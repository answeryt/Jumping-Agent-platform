from __future__ import annotations

import asyncio
import http.client
import importlib.util
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sandbox_manager import SandboxInstance, SandboxManager

try:
    from backend.memory.memory_template_writer import AgentOutputRecord, update_memory_template
except ModuleNotFoundError:
    from memory.memory_template_writer import AgentOutputRecord, update_memory_template


_THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _THIS_DIR.parent
AGENT_BUILDER_ROOT = PROJECT_ROOT / "agent_builder"
WORKSPACE_DIR = _THIS_DIR / "workspace"
REACT_AGENT_API_URL = "http://localhost:8000/chat"
MEMORY_TEMPLATE_PATH = PROJECT_ROOT / "backend" / "memory" / "memory_templete.md"


def _load_builder_module(rel_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, AGENT_BUILDER_ROOT / rel_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load builder module: {rel_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _slugify(value: str, default: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower().replace("-", "_"))
    normalized = re.sub(r"_+", "_", raw).strip("_")
    return normalized or default


def _dedupe_name(candidate: str, used: set[str]) -> str:
    if candidate not in used:
        used.add(candidate)
        return candidate

    suffix = 2
    while f"{candidate}_{suffix}" in used:
        suffix += 1
    unique = f"{candidate}_{suffix}"
    used.add(unique)
    return unique


class _ExecResult:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class LocalExecutor:
    _PREFIX = "/workspace/"

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def _to_local(self, container_path: str) -> Path:
        if container_path.startswith(self._PREFIX):
            rel = container_path[len(self._PREFIX) :]
        else:
            rel = container_path.lstrip("/")
        return self.base_dir / rel

    def run(self, command: list[str], **_kwargs: Any) -> _ExecResult:
        if command[:2] == ["test", "-f"]:
            exists = self._to_local(command[2]).exists()
            return _ExecResult(returncode=0 if exists else 1)
        if command[:2] == ["mkdir", "-p"]:
            self._to_local(command[2]).mkdir(parents=True, exist_ok=True)
            return _ExecResult()
        return _ExecResult()

    def write_file(self, container_path: str, content: str) -> _ExecResult:
        local = self._to_local(container_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(content, encoding="utf-8")
        return _ExecResult()


class Position(BaseModel):
    x: float = 0
    y: float = 0


class AgentNodeConfig(BaseModel):
    name: str = ""
    responsibility: str = ""
    deliverable: Literal["plan", "analysis", "artifact", "review"] = "analysis"
    modelProfile: Literal["balanced", "reasoning", "fast"] = "balanced"
    autonomy: Literal["structured", "adaptive"] = "structured"
    guidance: str = ""
    tools: List[Literal["browser", "vscode", "jupyter"]] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    type: Literal["agent", "user"]
    label: str = ""
    shape: str = ""
    position: Position = Field(default_factory=Position)
    config: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    mode: Literal["static", "dynamic"]
    style: str = ""


class GraphSpec(BaseModel):
    projectId: str = ""
    projectName: str = ""
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class CreateAgentRequest(BaseModel):
    agent_name: str


class CreateAgentResponse(BaseModel):
    workspace: str
    generated_files: List[str]
    answer: str
    sandboxes: List[Dict[str, Any]] = Field(default_factory=list)


class RegisteredAgent(BaseModel):
    id: str
    project: str
    agentName: str
    label: str
    sandboxTools: List[str] = Field(default_factory=list)
    sandbox: Optional[Dict[str, Any]] = None


class ListAgentsResponse(BaseModel):
    agents: List[RegisteredAgent] = Field(default_factory=list)


@dataclass
class AgentBuildSpec:
    node_id: str
    agent_name: str
    label: str
    config: AgentNodeConfig
    upstream_nodes: List[str]
    static_downstream_agents: List[str]
    dynamic_downstream_agents: List[str]


@dataclass
class FlowBuildSpec:
    flow_type: Literal["sequential", "router"]
    filename: str
    content: str
    details: Dict[str, Any]


@dataclass
class BuildPlan:
    project_name: str
    graph: GraphSpec
    agent_specs: List[AgentBuildSpec]
    flow_spec: Optional[FlowBuildSpec]
    warnings: List[str]


app = FastAPI(title="Agent Orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:6300",
        "http://127.0.0.1:6300",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_registered_agents_from_workspace() -> List[RegisteredAgent]:
    if not WORKSPACE_DIR.exists():
        return []

    agents: List[RegisteredAgent] = []
    for project_dir in sorted(path for path in WORKSPACE_DIR.iterdir() if path.is_dir()):
        plan_path = project_dir / "build_plan.json"
        if not plan_path.exists():
            continue

        try:
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        raw_agents = payload.get("agents")
        if not isinstance(raw_agents, list):
            continue

        for item in raw_agents:
            if not isinstance(item, dict):
                continue
            agent_name = item.get("agent_name")
            if not isinstance(agent_name, str) or not agent_name.strip():
                continue
            label_value = item.get("label")
            label = label_value if isinstance(label_value, str) and label_value.strip() else agent_name
            config = item.get("config")
            raw_tools = config.get("tools") if isinstance(config, dict) else []
            sandbox_tools = [
                tool
                for tool in raw_tools
                if isinstance(tool, str) and tool in {"browser", "vscode", "jupyter"}
            ] if isinstance(raw_tools, list) else []
            sandbox = item.get("sandbox")
            project = project_dir.name
            agents.append(
                RegisteredAgent(
                    id=f"{project}:{agent_name}",
                    project=project,
                    agentName=agent_name,
                    label=label,
                    sandboxTools=sandbox_tools,
                    sandbox=sandbox if isinstance(sandbox, dict) else None,
                )
            )
    return agents


@app.get("/my-agents", response_model=ListAgentsResponse)
async def list_my_agents() -> ListAgentsResponse:
    return ListAgentsResponse(agents=_load_registered_agents_from_workspace())


def _ensure_safe_workspace_path(workspace_dir: Path) -> None:
    workspace_root = WORKSPACE_DIR.resolve()
    candidate = workspace_dir.resolve()
    if candidate != workspace_root and workspace_root not in candidate.parents:
        raise RuntimeError(f"Refusing to operate outside workspace root: {candidate}")


def _prepare_workspace(project_name: str) -> Path:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    workspace_dir = WORKSPACE_DIR / project_name
    _ensure_safe_workspace_path(workspace_dir)

    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


def _graph_to_node_map(graph: GraphSpec) -> Dict[str, GraphNode]:
    node_map: Dict[str, GraphNode] = {}
    for node in graph.nodes:
        if node.id in node_map:
            raise ValueError(f"Duplicate node id: {node.id}")
        node_map[node.id] = node
    return node_map


def _resolve_agent_specs(graph: GraphSpec, node_map: Dict[str, GraphNode]) -> List[AgentBuildSpec]:
    agent_nodes = [node for node in graph.nodes if node.type == "agent"]
    if not agent_nodes:
        raise ValueError("Graph must contain at least one agent node")

    used_names: set[str] = set()
    upstream_by_node: Dict[str, List[str]] = {}
    static_targets_by_node: Dict[str, List[str]] = {}
    dynamic_targets_by_node: Dict[str, List[str]] = {}

    for edge in graph.edges:
        source = node_map.get(edge.source)
        target = node_map.get(edge.target)
        if source is None or target is None:
            raise ValueError(f"Edge references missing nodes: {edge.id}")
        upstream_by_node.setdefault(target.id, []).append(source.id)
        if edge.mode == "static" and source.type == "agent" and target.type == "agent":
            static_targets_by_node.setdefault(source.id, []).append(target.id)
        if edge.mode == "dynamic":
            if source.type != "agent" or target.type != "agent":
                raise ValueError("Dynamic edges must connect agent nodes only")
            dynamic_targets_by_node.setdefault(source.id, []).append(target.id)

    specs: List[AgentBuildSpec] = []
    for index, node in enumerate(agent_nodes, start=1):
        config = AgentNodeConfig.model_validate(node.config or {})
        base_name = config.name or node.label or f"agent_{index}"
        agent_name = _dedupe_name(_slugify(base_name, f"agent_{index}"), used_names)
        specs.append(
            AgentBuildSpec(
                node_id=node.id,
                agent_name=agent_name,
                label=node.label or agent_name.replace("_", " ").title(),
                config=config,
                upstream_nodes=upstream_by_node.get(node.id, []),
                static_downstream_agents=static_targets_by_node.get(node.id, []),
                dynamic_downstream_agents=dynamic_targets_by_node.get(node.id, []),
            )
        )
    return specs


def _resolve_project_name(graph: GraphSpec) -> str:
    base = graph.projectName or graph.projectId or "canvas_project"
    return _slugify(base, "canvas_project")


def _resolve_model_name(profile: Literal["balanced", "reasoning", "fast"]) -> str:
    return {
        "balanced": "gpt-4.1-mini",
        "reasoning": "gpt-4.1",
        "fast": "gpt-4o-mini",
    }[profile]


def _describe_deliverable(deliverable: Literal["plan", "analysis", "artifact", "review"]) -> str:
    return {
        "plan": "Produce a concrete execution plan or task breakdown.",
        "analysis": "Produce a clear analysis or synthesized explanation.",
        "artifact": "Produce a concrete artifact such as code, copy, or structured output.",
        "review": "Produce review feedback, validation notes, or approval guidance.",
    }[deliverable]


def _describe_autonomy(autonomy: Literal["structured", "adaptive"]) -> str:
    return {
        "structured": "Stay close to explicit graph edges and deterministic handoffs.",
        "adaptive": "Use more runtime judgment when deciding how to route work through dynamic edges.",
    }[autonomy]


def _infer_agent_role(agent_spec: AgentBuildSpec) -> str:
    upstream_count = len(agent_spec.upstream_nodes)
    static_count = len(agent_spec.static_downstream_agents)
    dynamic_count = len(agent_spec.dynamic_downstream_agents)

    if dynamic_count > 0 and static_count > 0:
        return "coordinator"
    if dynamic_count > 0:
        return "dispatcher"
    if upstream_count > 1 and static_count == 0:
        return "aggregator"
    if upstream_count == 0:
        return "entry"
    if static_count == 0:
        return "finalizer"
    return "worker"


def _describe_handoff_mode(agent_spec: AgentBuildSpec) -> str:
    if agent_spec.dynamic_downstream_agents and agent_spec.static_downstream_agents:
        return (
            "This agent coordinates both deterministic handoffs and dynamic dispatch candidates."
        )
    if agent_spec.dynamic_downstream_agents:
        return "This agent should choose among the candidate dynamic downstream agents at runtime."
    if agent_spec.static_downstream_agents:
        return "This agent should hand work to the next static downstream agent when appropriate."
    return "This agent is a terminal node and should produce a final output with no downstream handoff."


def _resolve_sequential_flow(
    agent_specs: List[AgentBuildSpec],
    node_map: Dict[str, GraphNode],
    edges: List[GraphEdge],
) -> Optional[FlowBuildSpec]:
    agent_names_by_id = {spec.node_id: spec.agent_name for spec in agent_specs}
    static_agent_edges = [
        edge
        for edge in edges
        if edge.mode == "static"
        and node_map[edge.source].type == "agent"
        and node_map[edge.target].type == "agent"
    ]

    if not static_agent_edges:
        return None

    indegree = {spec.node_id: 0 for spec in agent_specs}
    outdegree = {spec.node_id: 0 for spec in agent_specs}
    adjacency: Dict[str, List[str]] = {spec.node_id: [] for spec in agent_specs}

    for edge in static_agent_edges:
        indegree[edge.target] += 1
        outdegree[edge.source] += 1
        adjacency[edge.source].append(edge.target)

    if any(value > 1 for value in indegree.values()) or any(value > 1 for value in outdegree.values()):
        return None

    starts = [node_id for node_id, value in indegree.items() if value == 0]
    if len(starts) != 1:
        return None

    order: List[str] = []
    current = starts[0]
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        order.append(agent_names_by_id[current])
        next_nodes = adjacency.get(current, [])
        current = next_nodes[0] if next_nodes else ""

    if len(order) != len(agent_specs):
        return None

    flow_template = _load_builder_module("flow_template/flow_templete.py", "builder_flow_templates")
    content = flow_template.sequential_flow_py(order)
    return FlowBuildSpec(
        flow_type="sequential",
        filename="Workflow/sequential_flow.py",
        content=content,
        details={"agent_order": order},
    )


def _resolve_router_flow(
    agent_specs: List[AgentBuildSpec],
    node_map: Dict[str, GraphNode],
    edges: List[GraphEdge],
) -> Optional[FlowBuildSpec]:
    dynamic_agent_edges = [
        edge
        for edge in edges
        if edge.mode == "dynamic"
        and node_map[edge.source].type == "agent"
        and node_map[edge.target].type == "agent"
    ]
    if not dynamic_agent_edges:
        return None

    static_agent_edges = [
        edge
        for edge in edges
        if edge.mode == "static"
        and node_map[edge.source].type == "agent"
        and node_map[edge.target].type == "agent"
    ]
    if static_agent_edges:
        return None

    dynamic_sources = {edge.source for edge in dynamic_agent_edges}
    if len(dynamic_sources) != 1:
        return None

    agent_names_by_id = {spec.node_id: spec.agent_name for spec in agent_specs}
    dispatcher_id = next(iter(dynamic_sources))
    target_ids = [edge.target for edge in dynamic_agent_edges]
    involved_agent_ids = {dispatcher_id, *target_ids}
    if involved_agent_ids != set(agent_names_by_id):
        return None

    dispatcher_name = agent_names_by_id[dispatcher_id]
    targets = [agent_names_by_id[target_id] for target_id in target_ids]
    branches = {target: target for target in targets}

    flow_template = _load_builder_module("flow_template/flow_templete.py", "builder_flow_templates")
    content = flow_template.router_flow_py(dispatcher_name, branches)
    return FlowBuildSpec(
        flow_type="router",
        filename="Workflow/router_flow.py",
        content=content,
        details={"dispatcher": dispatcher_name, "branches": branches},
    )


def _plan_build(graph: GraphSpec) -> BuildPlan:
    node_map = _graph_to_node_map(graph)
    user_nodes = [node for node in graph.nodes if node.type == "user"]
    if not user_nodes:
        raise ValueError("Graph must contain at least one user node")

    agent_specs = _resolve_agent_specs(graph, node_map)
    warnings: List[str] = []

    flow_spec = _resolve_router_flow(agent_specs, node_map, graph.edges)
    if flow_spec is None:
        flow_spec = _resolve_sequential_flow(agent_specs, node_map, graph.edges)

    if flow_spec is None and graph.edges:
        warnings.append(
            "Graph edges were accepted, but automatic flow skeleton generation only supports linear static chains or a single dynamic dispatcher for now."
        )

    return BuildPlan(
        project_name=_resolve_project_name(graph),
        graph=graph,
        agent_specs=agent_specs,
        flow_spec=flow_spec,
        warnings=warnings,
    )


def _serialize_sandboxes(
    sandboxes_by_agent: Dict[str, SandboxInstance],
) -> List[Dict[str, Any]]:
    return [sandbox.model_dump() for sandbox in sandboxes_by_agent.values()]


def _summarize_build_plan(plan: BuildPlan) -> str:
    flow_type = plan.flow_spec.flow_type if plan.flow_spec else "none"
    return f"项目 {plan.project_name}，Agent 数量 {len(plan.agent_specs)}，Flow 类型 {flow_type}"


def _write_build_memory_context(
    *,
    plan: BuildPlan,
    task_status: str,
    agent_outputs: Dict[str, str],
    generated_files: List[str] | None = None,
) -> None:
    file_count = len(generated_files or [])
    summary = _summarize_build_plan(plan)
    if file_count:
        summary = f"{summary}，已生成文件 {file_count} 个"

    update_memory_template(
        template_path=MEMORY_TEMPLATE_PATH,
        task_goal=f"构建项目 {plan.project_name} 的 Agent 与工作流",
        task_status=task_status,
        key_info_summary=summary,
        agent_outputs=[
            AgentOutputRecord(agent_name=name, output=output)
            for name, output in agent_outputs.items()
        ],
        tool_call_total=len(agent_outputs),
    )


def _write_legacy_agent_memory_context(agent_name: str, answer: str) -> None:
    update_memory_template(
        template_path=MEMORY_TEMPLATE_PATH,
        task_goal=f"创建单个 Agent：{agent_name}",
        task_status="已完成",
        key_info_summary=f"后端已返回 Agent `{agent_name}` 的生成结果",
        agent_outputs=[AgentOutputRecord(agent_name=agent_name, output=answer)],
        tool_call_total=1,
    )


def _agent_requires_sandbox(agent_spec: AgentBuildSpec) -> bool:
    return bool(agent_spec.config.tools)


def _build_graph_context_markdown(
    plan: BuildPlan,
    agent_names_by_id: Dict[str, str],
    sandboxes_by_agent: Dict[str, SandboxInstance],
) -> str:
    agent_specs_by_id = {spec.node_id: spec for spec in plan.agent_specs}
    lines = [
        "# Build Context",
        "",
        f"- Project: `{plan.project_name}`",
        f"- Agents: `{len(plan.agent_specs)}`",
        f"- Flow skeleton: `{plan.flow_spec.flow_type if plan.flow_spec else 'none'}`",
        "",
        "## Nodes",
    ]

    for node in plan.graph.nodes:
        if node.type == "agent":
            agent_name = agent_names_by_id[node.id]
            agent_spec = agent_specs_by_id[node.id]
            sandbox = sandboxes_by_agent.get(agent_name)
            lines.extend(
                [
                    f"- Agent `{agent_name}`",
                    f"  - Source node id: `{node.id}`",
                    f"  - Label: `{node.label or agent_name}`",
                    f"  - Suggested role: `{_infer_agent_role(agent_spec)}`",
                    f"  - Responsibility: `{agent_spec.config.responsibility or 'auto'}`",
                    f"  - Deliverable: `{agent_spec.config.deliverable}`",
                    f"  - Model profile: `{agent_spec.config.modelProfile}`",
                    f"  - Autonomy: `{agent_spec.config.autonomy}`",
                    f"  - Sandbox tools: `{', '.join(agent_spec.config.tools) if agent_spec.config.tools else 'none'}`",
                ]
            )
            if sandbox is not None:
                lines.extend(
                    [
                        f"  - Sandbox base URL: `{sandbox.base_url}`",
                        f"  - Sandbox MCP URL: `{sandbox.mcp_url}`",
                        f"  - Sandbox dashboard: `{sandbox.dashboard_url}`",
                    ]
                )
            else:
                lines.append("  - Sandbox: `not allocated`")
            if agent_spec.config.guidance.strip():
                lines.append(f"  - Guidance: `{agent_spec.config.guidance.strip()}`")
        else:
            lines.extend(
                [
                    f"- User node `{node.id}`",
                    f"  - Label: `{node.label or 'User'}`",
                ]
            )

    lines.extend(["", "## Edges"])
    for edge in plan.graph.edges:
        lines.append(f"- `{edge.source}` -> `{edge.target}` ({edge.mode})")

    if plan.flow_spec:
        lines.extend(["", "## Flow Plan", f"- Type: `{plan.flow_spec.flow_type}`"])
        for key, value in plan.flow_spec.details.items():
            lines.append(f"- {key}: `{value}`")

    if plan.warnings:
        lines.extend(["", "## Warnings"])
        for warning in plan.warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def _build_agent_completion_task(
    agent_spec: AgentBuildSpec,
    plan: BuildPlan,
    workspace_dir: Path,
    agent_names_by_id: Dict[str, str],
    sandbox: Optional[SandboxInstance],
) -> str:
    upstream = [
        agent_names_by_id.get(node_id, node_id)
        for node_id in agent_spec.upstream_nodes
    ] or ["user"]
    static_downstream = [
        agent_names_by_id.get(node_id, node_id)
        for node_id in agent_spec.static_downstream_agents
    ] or ["none"]
    dynamic_downstream = [
        agent_names_by_id.get(node_id, node_id)
        for node_id in agent_spec.dynamic_downstream_agents
    ] or ["none"]
    inferred_role = _infer_agent_role(agent_spec)
    resolved_model = _resolve_model_name(agent_spec.config.modelProfile)
    responsibility = (
        agent_spec.config.responsibility.strip()
        or "Infer a pragmatic responsibility from the graph position and label."
    )
    guidance = agent_spec.config.guidance.strip() or "No additional guidance was provided."
    deliverable = _describe_deliverable(agent_spec.config.deliverable)
    autonomy = _describe_autonomy(agent_spec.config.autonomy)
    handoff_mode = _describe_handoff_mode(agent_spec)
    sandbox_tools = ", ".join(agent_spec.config.tools) if agent_spec.config.tools else "none"
    if sandbox is not None:
        sandbox_context = (
            f"Sandbox base URL: {sandbox.base_url}\n"
            f"Sandbox MCP URL: {sandbox.mcp_url}\n"
            f"Sandbox dashboard URL: {sandbox.dashboard_url}\n"
            f"Selected sandbox tools: {sandbox_tools}\n"
        )
        sandbox_rules = (
            "- Do not hard-code `http://localhost:8080`; use the sandbox URLs supplied for this agent.\n"
            "- Treat selected sandbox tools as AIO Sandbox capabilities: browser, VSCode, and Jupyter run inside this agent's dedicated sandbox.\n"
        )
    else:
        sandbox_context = (
            "Sandbox: not allocated\n"
            f"Selected sandbox tools: {sandbox_tools}\n"
        )
        sandbox_rules = (
            "- No sandbox tools were selected for this agent, so no dedicated AIO Sandbox was allocated.\n"
            "- Do not add browser, VSCode, Jupyter, MCP, or sandbox-specific behavior unless the skeleton already requires it.\n"
        )

    return (
        "[SELECT_SKILL]agent-dev-skill[/SELECT_SKILL]\n\n"
        "You are completing an agent code skeleton created from a canvas graph.\n\n"
        "Environment rules:\n"
        "- This machine is Windows.\n"
        "- Every path passed to tool_call must use forward slashes.\n"
        "- Modify files in place.\n\n"
        f"Project workspace: {workspace_dir.as_posix()}\n"
        f"Agent name: {agent_spec.agent_name}\n"
        f"Display label: {agent_spec.label}\n"
        f"Inferred graph role: {inferred_role}\n"
        f"Model profile: {agent_spec.config.modelProfile}\n"
        f"Resolved model target: {resolved_model}\n"
        f"Behavior mode: {agent_spec.config.autonomy}\n"
        f"{sandbox_context}"
        f"Upstream nodes: {', '.join(upstream)}\n"
        f"Static downstream agents: {', '.join(static_downstream)}\n"
        f"Dynamic downstream agents: {', '.join(dynamic_downstream)}\n"
        f"Project flow skeleton: {plan.flow_spec.flow_type if plan.flow_spec else 'none'}\n\n"
        "User-authored intent:\n"
        f"- Responsibility: {responsibility}\n"
        f"- Deliverable intent: {deliverable}\n"
        f"- Additional guidance: {guidance}\n\n"
        "System generation rules:\n"
        "- The end user does not author low-level context, trace, or handoff blocks directly.\n"
        "- Derive those structured sections from the graph, the build context markdown, and the standard template.\n"
        f"- Behavior mode guidance: {autonomy}\n"
        f"- Handoff guidance: {handoff_mode}\n\n"
        "Required steps:\n"
        f"1. tool_call(\"load_project\", \"{workspace_dir.as_posix()}\")\n"
        f"2. tool_call(\"get\", \"BUILD_CONTEXT.md\")\n"
        f"3. tool_call(\"get\", \"Agent/{agent_spec.agent_name}_agent.py\")\n"
        f"4. tool_call(\"get\", \"Prompt/{agent_spec.agent_name}_agent.md\")\n"
        "5. Update both files in place.\n\n"
        "Implementation requirements:\n"
        f"- Keep `Agent/{agent_spec.agent_name}_agent.py` compatible with the generated skeleton.\n"
        "- Implement only the minimal class logic expected by the skeleton.\n"
        f"- Put most role definition, collaboration rules, and handoff behavior into `Prompt/{agent_spec.agent_name}_agent.md`.\n"
        "- Do not create project-local Tool skeleton files or `Tools/*_tool.py` wiring.\n"
        f"{sandbox_rules}"
        "- Reflect the graph role: static downstream agents are deterministic handoffs; dynamic downstream agents are candidate sub-agents chosen at runtime.\n"
        "- If the user-authored responsibility is sparse, infer a pragmatic role from the label and graph position.\n\n"
        "Final Answer must summarize the files you changed."
    )


def _post_back_agent_chat_sync(user_input: str) -> str:
    body = json.dumps({"user_input": user_input}).encode("utf-8")
    request = urllib_request.Request(
        REACT_AGENT_API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"back_agent returned HTTP {exc.code}: {detail}"
        ) from exc
    except http.client.RemoteDisconnected as exc:
        raise RuntimeError(
            "back_agent closed the connection without an HTTP response. "
            "Check whether the service on http://localhost:8000/chat crashed or timed out."
        ) from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Failed to call back_agent: {exc}") from exc

    return str(payload.get("answer", "")).strip()


async def _post_back_agent_chat(user_input: str) -> str:
    return await asyncio.to_thread(_post_back_agent_chat_sync, user_input)


def _write_workspace_context_files(
    executor: LocalExecutor,
    plan: BuildPlan,
    agent_names_by_id: Dict[str, str],
    sandboxes_by_agent: Dict[str, SandboxInstance],
) -> List[str]:
    generated_files: List[str] = []
    graph_dump = json.dumps(plan.graph.model_dump(), ensure_ascii=False, indent=2)
    plan_dump = json.dumps(
        {
            "project_name": plan.project_name,
            "agents": [
                {
                    "node_id": spec.node_id,
                    "agent_name": spec.agent_name,
                    "label": spec.label,
                    "config": spec.config.model_dump(),
                    "upstream_nodes": spec.upstream_nodes,
                    "static_downstream_agents": spec.static_downstream_agents,
                    "dynamic_downstream_agents": spec.dynamic_downstream_agents,
                    "sandbox": (
                        sandboxes_by_agent[spec.agent_name].model_dump()
                        if spec.agent_name in sandboxes_by_agent
                        else None
                    ),
                }
                for spec in plan.agent_specs
            ],
            "flow": {
                "type": plan.flow_spec.flow_type,
                "details": plan.flow_spec.details,
            }
            if plan.flow_spec
            else None,
            "warnings": plan.warnings,
            "sandboxes": _serialize_sandboxes(sandboxes_by_agent),
        },
        ensure_ascii=False,
        indent=2,
    )
    context_md = _build_graph_context_markdown(plan, agent_names_by_id, sandboxes_by_agent)

    for container_path, content in (
        ("/workspace/graph_spec.json", graph_dump),
        ("/workspace/build_plan.json", plan_dump),
        ("/workspace/BUILD_CONTEXT.md", context_md),
    ):
        result = executor.write_file(container_path, content)
        if not result.ok:
            raise RuntimeError(f"Failed to write context file: {container_path}")
        generated_files.append(container_path[len("/workspace/") :])

    return generated_files


def _write_flow_file(executor: LocalExecutor, flow_spec: FlowBuildSpec) -> str:
    container_path = f"/workspace/{flow_spec.filename}"
    result = executor.write_file(container_path, flow_spec.content)
    if not result.ok:
        raise RuntimeError(f"Failed to write flow file: {flow_spec.filename}")
    return flow_spec.filename


async def _send_event(
    websocket: WebSocket,
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    await websocket.send_json({"type": event_type, "payload": payload})


async def _emit_stage(websocket: WebSocket, stage: str, message: str, **extra: Any) -> None:
    payload = {"stage": stage, "message": message}
    payload.update(extra)
    await _send_event(websocket, "build.stage", payload)


async def _execute_graph_build(websocket: WebSocket, graph: GraphSpec) -> None:
    plan = _plan_build(graph)
    agent_builder = _load_builder_module("agent_create/create_agent.py", "builder_create_agent")
    workspace_dir = _prepare_workspace(plan.project_name)
    executor = LocalExecutor(workspace_dir)
    agent_names_by_id = {spec.node_id: spec.agent_name for spec in plan.agent_specs}
    generated_files: List[str] = []
    back_agent_answers: Dict[str, str] = {}
    sandbox_manager = SandboxManager()
    sandbox_agent_specs = [spec for spec in plan.agent_specs if _agent_requires_sandbox(spec)]

    await _send_event(
        websocket,
        "build.accepted",
        {
            "projectName": plan.project_name,
            "agentCount": len(plan.agent_specs),
            "flowType": plan.flow_spec.flow_type if plan.flow_spec else None,
            "warnings": plan.warnings,
        },
    )
    _write_build_memory_context(
        plan=plan,
        task_status="构建中",
        agent_outputs=back_agent_answers,
        generated_files=generated_files,
    )

    if sandbox_agent_specs:
        await _emit_stage(
            websocket,
            "creating_agent_sandboxes",
            "Starting AIO Sandbox Docker containers for agents with selected sandbox tools.",
        )
        sandboxes_by_agent = await asyncio.to_thread(
            sandbox_manager.ensure_agent_sandboxes,
            project_name=plan.project_name,
            agents=[(spec.node_id, spec.agent_name) for spec in sandbox_agent_specs],
        )
        for spec in sandbox_agent_specs:
            sandbox = sandboxes_by_agent[spec.agent_name]
            await _send_event(
                websocket,
                "agent.sandbox.created",
                {
                    "nodeId": spec.node_id,
                    "agentName": spec.agent_name,
                    "tools": spec.config.tools,
                    **sandbox.model_dump(),
                },
            )
    else:
        sandboxes_by_agent = {}
        await _emit_stage(
            websocket,
            "skipping_agent_sandboxes",
            "No sandbox tools were selected, so no AIO Sandbox containers were started.",
        )

    await _emit_stage(websocket, "planning_generation", "Graph validated and build plan created.")
    generated_files.extend(
        _write_workspace_context_files(
            executor,
            plan,
            agent_names_by_id,
            sandboxes_by_agent,
        )
    )

    await _emit_stage(websocket, "creating_agent_skeletons", "Creating agent skeleton files.")
    for spec in plan.agent_specs:
        agent_builder.create_agent(spec.agent_name, executor=executor)
        generated_files.extend(
            [
                f"Agent/{spec.agent_name}_agent.py",
                f"Prompt/{spec.agent_name}_agent.md",
            ]
        )
        await _send_event(
            websocket,
            "agent.skeleton.created",
            {
                "nodeId": spec.node_id,
                "agentName": spec.agent_name,
                "label": spec.label,
            },
        )

    if plan.flow_spec is not None:
        await _emit_stage(
            websocket,
            "creating_flow_skeleton",
            f"Generating {plan.flow_spec.flow_type} flow skeleton.",
            flowType=plan.flow_spec.flow_type,
        )
        generated_files.append(_write_flow_file(executor, plan.flow_spec))
        await _send_event(
            websocket,
            "flow.generated",
            {
                "flowType": plan.flow_spec.flow_type,
                "file": plan.flow_spec.filename,
                "details": plan.flow_spec.details,
            },
        )

    await _emit_stage(websocket, "back_agent_coding", "Sending agent skeletons to back_agent.")
    for spec in plan.agent_specs:
        await _send_event(
            websocket,
            "agent.codegen.started",
            {
                "nodeId": spec.node_id,
                "agentName": spec.agent_name,
            },
        )
        task = _build_agent_completion_task(
            spec,
            plan,
            workspace_dir,
            agent_names_by_id,
            sandboxes_by_agent.get(spec.agent_name),
        )
        answer = await _post_back_agent_chat(task)
        back_agent_answers[spec.agent_name] = answer
        _write_build_memory_context(
            plan=plan,
            task_status="构建中",
            agent_outputs=back_agent_answers,
            generated_files=generated_files,
        )
        await _send_event(
            websocket,
            "agent.codegen.finished",
            {
                "nodeId": spec.node_id,
                "agentName": spec.agent_name,
                "summary": answer,
            },
        )

    build_report = json.dumps(
        {
            "workspace": workspace_dir.as_posix(),
            "generated_files": generated_files,
            "back_agent_answers": back_agent_answers,
            "warnings": plan.warnings,
            "sandboxes": _serialize_sandboxes(sandboxes_by_agent),
        },
        ensure_ascii=False,
        indent=2,
    )
    executor.write_file("/workspace/build_report.json", build_report)
    generated_files.append("build_report.json")
    _write_build_memory_context(
        plan=plan,
        task_status="已完成",
        agent_outputs=back_agent_answers,
        generated_files=generated_files,
    )

    await _send_event(
        websocket,
        "build.finished",
        {
            "workspace": workspace_dir.as_posix(),
            "generatedFiles": generated_files,
            "warnings": plan.warnings,
            "flowType": plan.flow_spec.flow_type if plan.flow_spec else None,
            "sandboxes": _serialize_sandboxes(sandboxes_by_agent),
        },
    )


@app.websocket("/ws/project-build")
async def project_build_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    current_graph: Optional[GraphSpec] = None
    current_plan: Optional[BuildPlan] = None

    await _send_event(
        websocket,
        "hello.ack",
        {
            "service": "Agent Orchestrator",
            "supports": ["graph.submit", "build.start", "ping"],
        },
    )

    try:
        while True:
            raw_message = await websocket.receive_json()
            message_type = str(raw_message.get("type", "")).strip()
            payload = raw_message.get("payload") or {}

            if message_type == "ping":
                await _send_event(websocket, "pong", {})
                continue

            if message_type == "graph.submit":
                try:
                    current_graph = GraphSpec.model_validate(payload)
                    current_plan = _plan_build(current_graph)
                except Exception as exc:
                    await _send_event(
                        websocket,
                        "graph.invalid",
                        {"error": str(exc)},
                    )
                    continue

                await _send_event(
                    websocket,
                    "graph.validated",
                    {
                        "projectName": current_plan.project_name,
                        "agentCount": len(current_plan.agent_specs),
                        "warnings": current_plan.warnings,
                        "flowType": current_plan.flow_spec.flow_type if current_plan.flow_spec else None,
                        "agents": [
                            {
                                "nodeId": spec.node_id,
                                "agentName": spec.agent_name,
                                "label": spec.label,
                            }
                            for spec in current_plan.agent_specs
                        ],
                    },
                )
                continue

            if message_type == "build.start":
                if current_graph is None:
                    graph_payload = payload.get("graph")
                    if graph_payload is None:
                        await _send_event(
                            websocket,
                            "error",
                            {"message": "No graph has been submitted yet."},
                        )
                        continue
                    current_graph = GraphSpec.model_validate(graph_payload)

                try:
                    await _execute_graph_build(websocket, current_graph)
                    current_plan = _plan_build(current_graph)
                except Exception as exc:
                    await _send_event(
                        websocket,
                        "build.failed",
                        {"error": str(exc)},
                    )
                continue

            await _send_event(
                websocket,
                "error",
                {"message": f"Unsupported message type: {message_type}"},
            )
    except WebSocketDisconnect:
        return


def _build_legacy_completion_task(
    agent_name: str,
    workspace_dir: Path,
    sandbox: Optional[SandboxInstance] = None,
) -> str:
    agent_label = agent_name.replace("_", " ").title() + " Agent"
    if sandbox is not None:
        sandbox_context = (
            f"- Sandbox base URL: {sandbox.base_url}\n"
            f"- Sandbox MCP URL: {sandbox.mcp_url}\n"
            f"- Sandbox dashboard URL: {sandbox.dashboard_url}\n"
            "- Do not hard-code `http://localhost:8080`; use this agent's sandbox URLs.\n"
        )
    else:
        sandbox_context = (
            "- Sandbox: not allocated\n"
            "- No sandbox tools were selected for this agent.\n"
        )

    return (
        "[SELECT_SKILL]agent-dev-skill[/SELECT_SKILL]\n\n"
        "Complete the generated agent skeleton in this workspace.\n"
        "- Use forward slashes in every tool_call path.\n"
        f"- Workspace: {workspace_dir.as_posix()}\n"
        f"- Agent: {agent_name}\n"
        f"- Label: {agent_label}\n"
        f"{sandbox_context}"
        "\n"
        "Steps:\n"
        f"1. tool_call(\"load_project\", \"{workspace_dir.as_posix()}\")\n"
        f"2. tool_call(\"get\", \"Agent/{agent_name}_agent.py\")\n"
        f"3. tool_call(\"get\", \"Prompt/{agent_name}_agent.md\")\n"
        "4. Update the files in place.\n\n"
        "Final Answer must summarize the edits."
    )


@app.post("/create-agent", response_model=CreateAgentResponse)
async def create_agent(request: CreateAgentRequest) -> CreateAgentResponse:
    agent_name = _slugify(request.agent_name, "agent")
    workspace_dir = _prepare_workspace(agent_name)
    executor = LocalExecutor(workspace_dir)

    agent_builder = _load_builder_module("agent_create/create_agent.py", "legacy_builder_create_agent")
    sandboxes_by_agent: Dict[str, SandboxInstance] = {}

    agent_builder.create_agent(agent_name, executor=executor)
    generated_files = [
        f"Agent/{agent_name}_agent.py",
        f"Prompt/{agent_name}_agent.md",
    ]

    answer = await _post_back_agent_chat(
        _build_legacy_completion_task(agent_name, workspace_dir),
    )
    _write_legacy_agent_memory_context(agent_name, answer)

    return CreateAgentResponse(
        workspace=workspace_dir.as_posix(),
        generated_files=generated_files,
        answer=answer,
        sandboxes=_serialize_sandboxes(sandboxes_by_agent),
    )
