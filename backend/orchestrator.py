from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = BACKEND_ROOT / "workspace"
AGENT_BUILDER_ROOT = PROJECT_ROOT / "agent_builder"
BACK_AGENT_API_URL = os.getenv("REACT_AGENT_API_URL", "http://localhost:8000/chat")
WEIXIN_BRIDGE_URL = os.getenv("WEIXIN_BRIDGE_URL", "http://localhost:8787").rstrip("/")
WEIXIN_BRIDGE_ROOT = PROJECT_ROOT / "apps" / "weixin-main"
WEIXIN_BRIDGE_SOURCE = WEIXIN_BRIDGE_ROOT / "src" / "bridge" / "server.ts"
WEIXIN_BRIDGE_DIST = WEIXIN_BRIDGE_ROOT / "dist" / "src" / "bridge" / "server.js"
WEIXIN_BRIDGE_LOG_PATH = Path(
    os.getenv("WEIXIN_BRIDGE_LOG_PATH", str(BACKEND_ROOT / "logs" / "weixin-bridge.log"))
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


WEIXIN_BRIDGE_AUTO_START = _env_bool("WEIXIN_BRIDGE_AUTO_START", True)
WEIXIN_BRIDGE_AUTO_BUILD = _env_bool("WEIXIN_BRIDGE_AUTO_BUILD", True)
_WEIXIN_BRIDGE_PROCESS: Optional[subprocess.Popen[Any]] = None
_WEIXIN_BRIDGE_LOG_HANDLE: Optional[Any] = None

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(AGENT_BUILDER_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_BUILDER_ROOT))

from agent_builder.agent_template.agent_templete import agent_py, prompt_md
from agent_builder.common.naming import normalize_python_name, to_class_prefix
from agent_builder.config_template.config_templete import model_config_toml
from agent_builder.flow_template import (
    debate_flow_py,
    hierarchical_flow_py,
    loop_flow_py,
    parallel_flow_py,
    router_flow_py,
    sequential_flow_py,
    supervisor_flow_py,
)
from agent_builder.project_template.project_templete import RUNTIME_PROJECT_DIRS, RUNTIME_PROJECT_FILES
from agent_builder.run_time_templete.creat_runtime import runtime_files
from backend.set_agent_api_key import auto_update_workspace_from_configured_key
from backend.tools.catalog import available_default_tool_names


class AgentNodeConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str = ""
    responsibility: str = ""
    deliverable: str = ""
    model_profile: str = Field(default="balanced", alias="modelProfile")
    autonomy: str = "structured"
    guidance: str = ""
    tools: List[Any] = Field(default_factory=list)
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class GraphNode(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    type: str
    label: str = ""
    shape: Optional[str] = None
    position: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    source: str
    target: str
    mode: str = "static"
    flow_type: Optional[str] = Field(default=None, alias="flowType")
    style: Optional[str] = None


class GraphSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    project_id: Optional[str] = Field(default=None, alias="projectId")
    project_name: str = Field(default="agent_project", alias="projectName")
    task: str = ""
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


class AgentBuildSpec(BaseModel):
    node_id: str
    agent_name: str
    label: str
    config: AgentNodeConfig
    upstream_nodes: List[str] = Field(default_factory=list)
    static_downstream_agents: List[str] = Field(default_factory=list)
    dynamic_downstream_agents: List[str] = Field(default_factory=list)


class FlowBuildSpec(BaseModel):
    flow_type: str
    filename: str
    details: Dict[str, Any] = Field(default_factory=dict)


class BuildPlan(BaseModel):
    project_name: str
    graph: GraphSpec
    agent_specs: List[AgentBuildSpec]
    flow_spec: Optional[FlowBuildSpec] = None
    warnings: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    runtime_root: Path


class CreateAgentRequest(BaseModel):
    agent_name: str
    task: str = ""
    tools: List[Any] = Field(default_factory=list)


class BuildResponse(BaseModel):
    workspace: str
    generated_files: List[str]
    answer: str
    project_name: str
    build_plan: Dict[str, Any]


class ChatHistoryItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    human: Optional[str] = None
    assistant: Optional[str] = None
    role: Optional[str] = None
    content: Optional[str] = None


class WorkspaceChatRequest(BaseModel):
    user_input: str
    history: List[ChatHistoryItem] = Field(default_factory=list)
    workspace: Optional[str] = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    big_session_id: Optional[str] = None
    small_session_id: Optional[str] = None


class WorkspaceChatResponse(BaseModel):
    answer: str
    workspace: str
    user_id: str
    big_session_id: str
    small_session_id: str
    memory_md_path: str


class NewSessionRequest(BaseModel):
    workspace: Optional[str] = None
    user_id: Optional[str] = None


class NewSessionResponse(BaseModel):
    big_session_id: str
    user_id: str


class WeixinLoginStartRequest(BaseModel):
    workspace: str
    force: bool = False


class WeixinAccountStartRequest(BaseModel):
    workspace: str


def _dump_model(model: BaseModel, *, by_alias: bool = False) -> Dict[str, Any]:
    return model.model_dump(by_alias=by_alias)


def _agent_nodes(graph: GraphSpec) -> List[GraphNode]:
    return [node for node in graph.nodes if node.type.lower() == "agent"]


def _node_name(node: GraphNode) -> str:
    configured = str(node.config.get("name") or "").strip()
    raw = configured or node.label or node.id
    return normalize_python_name(raw, "agent")


def _agent_name_map(graph: GraphSpec) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    used: Dict[str, int] = {}
    for node in graph.nodes:
        if node.type.lower() != "agent":
            mapping[node.id] = node.id
            continue
        base = _node_name(node)
        count = used.get(base, 0)
        used[base] = count + 1
        mapping[node.id] = base if count == 0 else f"{base}_{count + 1}"
    return mapping


def _normalize_flow_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).strip().lower().replace("-", "_")
    aliases = {
        "sequence": "sequential",
        "sequential_chain": "sequential",
        "routing": "router",
        "route": "router",
        "fanout": "parallel",
        "fan_out": "parallel",
        "reflection": "loop",
        "iterate": "loop",
        "hierarchy": "hierarchical",
    }
    return aliases.get(normalized, normalized)


def _declared_flow_type(graph: GraphSpec, agent_count: int) -> Optional[str]:
    for edge in graph.edges:
        flow_type = _normalize_flow_type(edge.flow_type or edge.style)
        if flow_type:
            return flow_type
    if agent_count > 1:
        return "sequential"
    return None


def _outgoing(edges: Iterable[GraphEdge], node_id: str) -> List[GraphEdge]:
    return [edge for edge in edges if edge.source == node_id]


def _incoming(edges: Iterable[GraphEdge], node_id: str) -> List[GraphEdge]:
    return [edge for edge in edges if edge.target == node_id]


def _ordered_agents_from_edges(graph: GraphSpec, agent_names_by_id: Dict[str, str]) -> List[str]:
    agent_ids = {node.id for node in _agent_nodes(graph)}
    if not agent_ids:
        return []

    user_edges = [edge for edge in graph.edges if edge.source not in agent_ids and edge.target in agent_ids]
    start = user_edges[0].target if user_edges else next(iter(agent_ids))
    ordered_ids: List[str] = []
    seen: set[str] = set()
    current = start
    while current in agent_ids and current not in seen:
        ordered_ids.append(current)
        seen.add(current)
        next_edges = [edge for edge in _outgoing(graph.edges, current) if edge.target in agent_ids]
        if len(next_edges) != 1:
            break
        current = next_edges[0].target

    for node in _agent_nodes(graph):
        if node.id not in seen:
            ordered_ids.append(node.id)
    return [agent_names_by_id[node_id] for node_id in ordered_ids]


def _tool_name_from_payload(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("name", "tool_name", "toolName", "id"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _normalize_tool_names(raw_tools: Any) -> List[str]:
    items = raw_tools if isinstance(raw_tools, list) else []
    normalized: List[str] = []
    seen: set[str] = set()
    for item in items:
        name = _tool_name_from_payload(item)
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def _normalize_agent_config_payload(config_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(config_payload)
    payload["tools"] = _normalize_tool_names(payload.get("tools", []))
    return payload


def _build_agent_specs(graph: GraphSpec, agent_names_by_id: Dict[str, str]) -> List[AgentBuildSpec]:
    agent_ids = {node.id for node in _agent_nodes(graph)}
    specs: List[AgentBuildSpec] = []
    for node in _agent_nodes(graph):
        config_payload = {**node.config, "name": agent_names_by_id[node.id]}
        config_payload = _normalize_agent_config_payload(config_payload)
        cfg = AgentNodeConfig.model_validate(config_payload)
        upstream = [edge.source for edge in _incoming(graph.edges, node.id)]
        static_downstream = [
            edge.target
            for edge in _outgoing(graph.edges, node.id)
            if edge.target in agent_ids and edge.mode != "dynamic"
        ]
        dynamic_downstream = [
            edge.target
            for edge in _outgoing(graph.edges, node.id)
            if edge.target in agent_ids and edge.mode == "dynamic"
        ]
        specs.append(
            AgentBuildSpec(
                node_id=node.id,
                agent_name=agent_names_by_id[node.id],
                label=node.label or agent_names_by_id[node.id],
                config=cfg,
                upstream_nodes=upstream,
                static_downstream_agents=static_downstream,
                dynamic_downstream_agents=dynamic_downstream,
            )
        )
    return specs


def _router_flow_spec(graph: GraphSpec, names: Dict[str, str]) -> FlowBuildSpec:
    agent_ids = {node.id for node in _agent_nodes(graph)}
    candidates = [
        node_id
        for node_id in agent_ids
        if len([edge for edge in _outgoing(graph.edges, node_id) if edge.target in agent_ids]) >= 2
    ]
    dispatcher_id = candidates[0] if candidates else _agent_nodes(graph)[0].id
    branches = {
        names[edge.target]: names[edge.target]
        for edge in _outgoing(graph.edges, dispatcher_id)
        if edge.target in agent_ids
    }
    return FlowBuildSpec(
        flow_type="router",
        filename="Workflow/router_flow.py",
        details={"dispatcher": names[dispatcher_id], "branches": branches},
    )


def _parallel_flow_spec(graph: GraphSpec, names: Dict[str, str]) -> FlowBuildSpec:
    agent_ids = {node.id for node in _agent_nodes(graph)}
    dispatcher_id = next(
        (
            node_id
            for node_id in agent_ids
            if len([edge for edge in _outgoing(graph.edges, node_id) if edge.target in agent_ids]) >= 2
        ),
        _agent_nodes(graph)[0].id,
    )
    worker_ids = [edge.target for edge in _outgoing(graph.edges, dispatcher_id) if edge.target in agent_ids]
    downstream_counts: Dict[str, int] = {}
    for worker_id in worker_ids:
        for edge in _outgoing(graph.edges, worker_id):
            if edge.target in agent_ids:
                downstream_counts[edge.target] = downstream_counts.get(edge.target, 0) + 1
    aggregator_id = max(downstream_counts, key=downstream_counts.get) if downstream_counts else _agent_nodes(graph)[-1].id
    workers = [names[node_id] for node_id in worker_ids if node_id != aggregator_id]
    return FlowBuildSpec(
        flow_type="parallel",
        filename="Workflow/parallel_flow.py",
        details={"dispatcher": names[dispatcher_id], "workers": workers, "aggregator": names[aggregator_id]},
    )


def _loop_flow_spec(graph: GraphSpec, names: Dict[str, str]) -> FlowBuildSpec:
    ordered = _ordered_agents_from_edges(graph, names)
    executor = ordered[0]
    evaluator = ordered[1] if len(ordered) > 1 else ordered[0]
    return FlowBuildSpec(
        flow_type="loop",
        filename="Workflow/loop_flow.py",
        details={"executor": executor, "evaluator": evaluator},
    )


def _debate_flow_spec(graph: GraphSpec, names: Dict[str, str]) -> FlowBuildSpec:
    agent_ids = {node.id for node in _agent_nodes(graph)}
    downstream_counts: Dict[str, int] = {}
    for edge in graph.edges:
        if edge.source in agent_ids and edge.target in agent_ids:
            downstream_counts[edge.target] = downstream_counts.get(edge.target, 0) + 1
    moderator_id = max(downstream_counts, key=downstream_counts.get) if downstream_counts else _agent_nodes(graph)[-1].id
    participants = [names[node.id] for node in _agent_nodes(graph) if node.id != moderator_id]
    return FlowBuildSpec(
        flow_type="debate",
        filename="Workflow/debate_flow.py",
        details={"participants": participants, "moderator": names[moderator_id]},
    )


def _hierarchical_flow_spec(graph: GraphSpec, names: Dict[str, str]) -> FlowBuildSpec:
    agent_ids = {node.id for node in _agent_nodes(graph)}
    manager_id = next(
        (
            node_id
            for node_id in agent_ids
            if len([edge for edge in _outgoing(graph.edges, node_id) if edge.target in agent_ids]) >= 1
        ),
        _agent_nodes(graph)[0].id,
    )
    workers = [names[edge.target] for edge in _outgoing(graph.edges, manager_id) if edge.target in agent_ids]
    if not workers:
        workers = [names[node.id] for node in _agent_nodes(graph) if node.id != manager_id]
    return FlowBuildSpec(
        flow_type="hierarchical",
        filename="Workflow/hierarchical_flow.py",
        details={"manager": names[manager_id], "workers": workers},
    )


def _supervisor_flow_spec(graph: GraphSpec, names: Dict[str, str]) -> FlowBuildSpec:
    ordered = _ordered_agents_from_edges(graph, names)
    supervisor = ordered[0]
    agents = [name for name in ordered[1:] if name != supervisor]
    return FlowBuildSpec(
        flow_type="supervisor",
        filename="Workflow/supervisor_flow.py",
        details={"supervisor": supervisor, "agents": agents},
    )


def _build_flow_spec(graph: GraphSpec, names: Dict[str, str]) -> Optional[FlowBuildSpec]:
    agent_count = len(_agent_nodes(graph))
    flow_type = _declared_flow_type(graph, agent_count)
    if flow_type is None:
        return None
    if flow_type == "sequential":
        return FlowBuildSpec(
            flow_type="sequential",
            filename="Workflow/sequential_flow.py",
            details={"order": _ordered_agents_from_edges(graph, names)},
        )
    if flow_type == "router":
        return _router_flow_spec(graph, names)
    if flow_type == "parallel":
        return _parallel_flow_spec(graph, names)
    if flow_type == "loop":
        return _loop_flow_spec(graph, names)
    if flow_type == "debate":
        return _debate_flow_spec(graph, names)
    if flow_type == "hierarchical":
        return _hierarchical_flow_spec(graph, names)
    if flow_type == "supervisor":
        return _supervisor_flow_spec(graph, names)
    return FlowBuildSpec(
        flow_type="sequential",
        filename="Workflow/sequential_flow.py",
        details={"order": _ordered_agents_from_edges(graph, names)},
    )


def _build_plan_from_graph(graph: GraphSpec) -> BuildPlan:
    names = _agent_name_map(graph)
    agent_specs = _build_agent_specs(graph, names)
    flow_spec = _build_flow_spec(graph, names)
    warnings: List[str] = []
    available_tools = set(available_default_tool_names())
    for spec in agent_specs:
        normalized = []
        invalid = []
        for tool_name in _normalize_tool_names(spec.config.tools):
            if tool_name in available_tools:
                normalized.append(tool_name)
            else:
                invalid.append(tool_name)
        spec.config.tools = normalized
        if invalid:
            warnings.append(
                f"agent {spec.agent_name} ignored unknown tools: {', '.join(invalid)}"
            )
    if not agent_specs:
        warnings.append("graph has no agent nodes")
    return BuildPlan(
        project_name=normalize_python_name(graph.project_name or graph.project_id or "agent_project", "project"),
        graph=graph,
        agent_specs=agent_specs,
        flow_spec=flow_spec,
        warnings=warnings,
    )


def _safe_project_dir(project_name: str) -> Path:
    base_name = normalize_python_name(project_name, "agent_project")
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    candidate = WORKSPACE_ROOT / base_name
    if not candidate.exists():
        return candidate
    suffix = time.strftime("%Y%m%d_%H%M%S")
    candidate = WORKSPACE_ROOT / f"{base_name}_{suffix}"
    index = 2
    while candidate.exists():
        candidate = WORKSPACE_ROOT / f"{base_name}_{suffix}_{index}"
        index += 1
    return candidate


def _write_text(path: Path, content: str, generated: List[str], root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    generated.append(path.relative_to(root).as_posix())


def _prompt_for_agent(spec: AgentBuildSpec, plan: BuildPlan) -> str:
    class_prefix = to_class_prefix(spec.agent_name, "agent")
    base = prompt_md(class_prefix, spec.agent_name)
    downstream = spec.static_downstream_agents + spec.dynamic_downstream_agents
    flow_type = plan.flow_spec.flow_type if plan.flow_spec else "single"
    additions = [
        "",
        "## Orchestrator Role Context",
        f"- Agent name: `{spec.agent_name}`",
        f"- Label: `{spec.label}`",
        f"- Flow type: `{flow_type}`",
        f"- Responsibility: {spec.config.responsibility or 'Complete this agent role.'}",
        f"- Deliverable: {spec.config.deliverable or 'useful final output'}",
        f"- Autonomy: {spec.config.autonomy}",
    ]
    if spec.config.guidance:
        additions.append(f"- Extra guidance: {spec.config.guidance}")
    if spec.config.tools:
        tool_names = ", ".join(spec.config.tools)
        additions.extend(
            [
                f"- Activated backend tools: {tool_names}",
                '- Tool call format: `tool_call("tool_name", key=value)`. Use only the activated tools listed above.',
            ]
        )
    else:
        additions.append("- Activated backend tools: none. Do not emit `tool_call(...)`.")
    if downstream:
        downstream_names = ", ".join(downstream)
        additions.append(f"- Downstream node ids: {downstream_names}")
    else:
        additions.append("- This agent is an end node or single-agent responder; prioritize a useful final answer.")
    return base.rstrip() + "\n" + "\n".join(additions).rstrip() + "\n"


def _flow_source(flow_spec: FlowBuildSpec) -> str:
    details = flow_spec.details
    if flow_spec.flow_type == "sequential":
        return sequential_flow_py(list(details.get("order", [])))
    if flow_spec.flow_type == "router":
        return router_flow_py(str(details["dispatcher"]), dict(details["branches"]))
    if flow_spec.flow_type == "parallel":
        return parallel_flow_py(str(details["dispatcher"]), list(details["workers"]), str(details["aggregator"]))
    if flow_spec.flow_type == "loop":
        return loop_flow_py(str(details["executor"]), str(details["evaluator"]))
    if flow_spec.flow_type == "debate":
        return debate_flow_py(list(details["participants"]), str(details["moderator"]))
    if flow_spec.flow_type == "hierarchical":
        return hierarchical_flow_py(str(details["manager"]), list(details["workers"]))
    if flow_spec.flow_type == "supervisor":
        return supervisor_flow_py(str(details["supervisor"]), list(details["agents"]))
    raise ValueError(f"unsupported flow type: {flow_spec.flow_type}")


def _build_plan_json(plan: BuildPlan) -> str:
    payload = {
        "project_name": plan.project_name,
        "flow": (
            {"type": plan.flow_spec.flow_type, "filename": plan.flow_spec.filename, **plan.flow_spec.details}
            if plan.flow_spec
            else {"type": "single"}
        ),
        "agents": [
            {
                "node_id": spec.node_id,
                "agent_name": spec.agent_name,
                "label": spec.label,
                "responsibility": spec.config.responsibility,
                "deliverable": spec.config.deliverable,
                "model_profile": spec.config.model_profile,
                "autonomy": spec.config.autonomy,
                "tools": spec.config.tools,
                "capabilities": spec.config.capabilities,
                "upstream_nodes": spec.upstream_nodes,
                "static_downstream_agents": spec.static_downstream_agents,
                "dynamic_downstream_agents": spec.dynamic_downstream_agents,
            }
            for spec in plan.agent_specs
        ],
        "warnings": plan.warnings,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _generate_workspace(plan: BuildPlan) -> tuple[ProjectPaths, List[str], Dict[str, str]]:
    project_root = _safe_project_dir(plan.project_name)
    runtime_root = project_root
    generated: List[str] = []

    for directory in RUNTIME_PROJECT_DIRS:
        (runtime_root / directory).mkdir(parents=True, exist_ok=True)

    for rel_path, content in {**RUNTIME_PROJECT_FILES, **runtime_files()}.items():
        _write_text(runtime_root / rel_path, content, generated, runtime_root)
    _write_text(runtime_root / "Config" / "model_config.toml", model_config_toml(), generated, runtime_root)
    auto_update_workspace_from_configured_key(runtime_root)

    agent_names_by_id = _agent_name_map(plan.graph)
    for spec in plan.agent_specs:
        class_prefix = to_class_prefix(spec.agent_name, "agent")
        prompt_file = f"{spec.agent_name}_agent.md"
        _write_text(runtime_root / "Agent" / f"{spec.agent_name}_agent.py", agent_py(class_prefix, spec.agent_name, prompt_file), generated, runtime_root)
        _write_text(runtime_root / "Prompt" / prompt_file, _prompt_for_agent(spec, plan), generated, runtime_root)

    if plan.flow_spec is not None:
        _write_text(runtime_root / plan.flow_spec.filename, _flow_source(plan.flow_spec), generated, runtime_root)

    _write_text(runtime_root / "build_plan.json", _build_plan_json(plan), generated, runtime_root)
    return ProjectPaths(project_root=project_root, runtime_root=runtime_root), generated, agent_names_by_id


def _build_workspace_completion_task(plan: BuildPlan, paths: ProjectPaths, agent_names_by_id: Dict[str, str]) -> str:
    flow_type = plan.flow_spec.flow_type if plan.flow_spec else "single"
    skill = "multi-agent-skill" if len(plan.agent_specs) > 1 else "single-agent-skill"
    agents = "\n".join(
        f"- {spec.agent_name}: {spec.config.responsibility or spec.label}"
        for spec in plan.agent_specs
    )
    flow_details = _dump_model(plan.flow_spec) if plan.flow_spec else {"type": "single"}
    return f"""[SELECT_SKILL]common-agent-skill[/SELECT_SKILL]
[SELECT_SKILL]{skill}[/SELECT_SKILL]

Treat the whole generated runtime as the unit of completion. Do not stop after completing only one agent file.

First identify the runtime's agent framework contract, including BaseAgent, PromptLoader, project_runtime, Flow, parser, and build_plan.json.
Keep all generated files compatible with that framework contract.
In multi-agent workspaces, express role differences through prompt, schema, flow, and handoff behavior, not by breaking required framework entrypoints.
Do not express role differences by omitting a required framework entrypoint.
If a generated node will be discovered or executed by the current framework, do not leave it in a half-implemented state.

Workspace directory: {paths.runtime_root.as_posix()}
Flow type: {flow_type}

Generated agents:
{agents or "- none"}

Flow details:
{json.dumps(flow_details, ensure_ascii=False, indent=2)}

Node id to agent name mapping:
{json.dumps(agent_names_by_id, ensure_ascii=False, indent=2)}

Task:
1. Call load_project on the workspace directory.
2. Inspect the generated runtime contract before editing.
3. Complete the generated Agent and Prompt files, and update flow/runtime files only if needed for compatibility.
4. Run syntax/import diagnostics when possible.
5. Return Final Answer with completed: true only after the workspace is coherent.
"""


def _build_legacy_completion_task(agent_name: str, tool_names: List[str], paths: ProjectPaths) -> str:
    del tool_names
    return f"""[SELECT_SKILL]common-agent-skill[/SELECT_SKILL]
[SELECT_SKILL]single-agent-skill[/SELECT_SKILL]

Complete the generated single-agent workspace for `{agent_name}`.

First identify the runtime's agent framework contract.
Keep the generated files compatible with that contract.
If a generated node will be discovered or executed by the current framework, do not leave it half-implemented.

Workspace directory: {paths.runtime_root.as_posix()}

Call load_project on the workspace directory, inspect the skeleton, complete the agent/prompt, and run diagnostics if possible.
"""


def _call_back_agent(task: str, timeout: int = 300) -> str:
    payload = json.dumps({"user_input": task}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BACK_AGENT_API_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"back_agent returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"back_agent is not reachable at {BACK_AGENT_API_URL}: {exc}") from exc

    data = json.loads(body or "{}")
    return str(data.get("answer", "")).strip()


def build_project_from_graph(graph: GraphSpec, *, call_completion: bool = True) -> BuildResponse:
    plan = _build_plan_from_graph(graph)
    if not plan.agent_specs:
        raise ValueError("graph must contain at least one agent node")

    paths, generated_files, agent_names_by_id = _generate_workspace(plan)
    answer = ""
    if call_completion:
        task = _build_workspace_completion_task(plan=plan, paths=paths, agent_names_by_id=agent_names_by_id)
        answer = _call_back_agent(task)
    return BuildResponse(
        workspace=str(paths.runtime_root),
        generated_files=sorted(generated_files),
        answer=answer,
        project_name=paths.project_root.name,
        build_plan=json.loads(_build_plan_json(plan)),
    )


def build_legacy_agent(agent_name: str, task: str = "", tools: Optional[List[Any]] = None) -> BuildResponse:
    graph = GraphSpec(
        projectName=agent_name,
        task=task,
        nodes=[
            GraphNode(id="user", type="user", label="User", config={}),
            GraphNode(
                id="agent",
                type="agent",
                label=agent_name,
                config={
                    "name": agent_name,
                    "responsibility": task or f"Complete the user's task as {agent_name}.",
                    "deliverable": "artifact",
                    "tools": tools or [],
                },
            ),
        ],
        edges=[GraphEdge(id="edge-1", source="user", target="agent", mode="static")],
    )
    plan = _build_plan_from_graph(graph)
    paths, generated_files, _agent_names_by_id = _generate_workspace(plan)
    task_text = _build_legacy_completion_task(
        agent_name=normalize_python_name(agent_name, "agent"),
        tool_names=[str(item.get("name", item)) if isinstance(item, dict) else str(item) for item in (tools or [])],
        paths=paths,
    )
    if task:
        task_text += f"\nUser requirement:\n{task}\n"
    answer = _call_back_agent(task_text)
    return BuildResponse(
        workspace=str(paths.runtime_root),
        generated_files=sorted(generated_files),
        answer=answer,
        project_name=paths.project_root.name,
        build_plan=json.loads(_build_plan_json(plan)),
    )


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _latest_workspace_dir() -> Path:
    candidates = [
        path
        for path in WORKSPACE_ROOT.iterdir()
        if path.is_dir() and (path / "project_runtime.py").exists()
    ] if WORKSPACE_ROOT.exists() else []
    if not candidates:
        raise FileNotFoundError("backend/workspace 中没有找到可运行的 Agent 工作区")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _resolve_workspace_dir(workspace: Optional[str]) -> Path:
    if not workspace or not str(workspace).strip():
        return _latest_workspace_dir().resolve()

    raw = Path(str(workspace).strip())
    path = raw if raw.is_absolute() else WORKSPACE_ROOT / raw
    path = path.resolve()
    workspace_root = WORKSPACE_ROOT.resolve()
    if not _path_is_relative_to(path, workspace_root):
        raise ValueError("workspace 必须位于 backend/workspace 内")
    if not (path / "project_runtime.py").exists():
        raise FileNotFoundError(f"workspace 不可运行或不存在: {path}")
    return path


def _normalize_chat_history(history: List[ChatHistoryItem]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for item in history:
        if item.human is not None or item.assistant is not None:
            human = str(item.human or "").strip()
            assistant = str(item.assistant or "").strip()
            if human:
                normalized.append({"role": "user", "content": human})
            if assistant:
                normalized.append({"role": "assistant", "content": assistant})
            continue

        role = str(item.role or "").strip()
        content = str(item.content or "").strip()
        if role and content:
            normalized.append({"role": role, "content": content})
    return normalized


def _load_workspace_runtime(workspace_dir: Path) -> Any:
    runtime_path = workspace_dir / "project_runtime.py"
    module_name = f"_workspace_project_runtime_{abs(hash(str(workspace_dir)))}_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(module_name, runtime_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 workspace runtime: {runtime_path}")

    runtime_modules = (
        "project_runtime",
        "Agent",
        "Model",
        "Workflow",
        "Config",
        "Context",
    )
    runtime_prefixes = tuple(prefix + "." for prefix in runtime_modules)
    for name in list(sys.modules):
        if name not in runtime_modules and not name.startswith(runtime_prefixes):
            continue
        sys.modules.pop(name, None)

    module = importlib.util.module_from_spec(spec)
    workspace_path = str(workspace_dir)
    if workspace_path in sys.path:
        sys.path.remove(workspace_path)
    sys.path.insert(0, workspace_path)
    spec.loader.exec_module(module)
    return module


def _allocate_big_session_id(existing: Optional[str]) -> str:
    from backend.memory.working_memory import SessionManager

    manager = SessionManager()
    if existing:
        return manager.resolve_big_session(existing)
    return manager.start_big_session()


def _runtime_chat_kwargs(
    runtime: Any,
    chat_fn: Any,
    request: WorkspaceChatRequest,
    *,
    user_id: str,
    big_session_id: str,
) -> Dict[str, Any]:
    candidates: Dict[str, Any] = {
        "history": _normalize_chat_history(request.history),
        "user_id": user_id,
        "big_session_id": big_session_id,
        "small_session_id": request.small_session_id,
        "return_session_info": True,
    }
    try:
        signature = inspect.signature(chat_fn)
    except (TypeError, ValueError):
        return candidates

    parameters = signature.parameters
    has_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values())
    if not has_var_kwargs:
        return {key: value for key, value in candidates.items() if key in parameters}

    run_project = getattr(runtime, "run_project_and_describe", None) or getattr(
        runtime, "run_project", None
    )
    if run_project is None:
        return candidates
    try:
        run_signature = inspect.signature(run_project)
    except (TypeError, ValueError):
        return candidates
    run_parameters = run_signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in run_parameters.values()):
        return candidates
    filtered = {
        key: value
        for key, value in candidates.items()
        if key in run_parameters or key == "return_session_info"
    }
    return filtered


def run_workspace_chat(request: WorkspaceChatRequest) -> WorkspaceChatResponse:
    workspace_dir = _resolve_workspace_dir(request.workspace)
    runtime = _load_workspace_runtime(workspace_dir)
    chat_fn = getattr(runtime, "chat", None)
    if chat_fn is None:
        raise RuntimeError(f"{workspace_dir} 未暴露 chat(user_input, **kwargs)")

    user_id = request.user_id or os.getenv("AGENT_DEFAULT_USER_ID", "ui_user")
    big_session_id = _allocate_big_session_id(request.big_session_id)

    outcome = chat_fn(
        request.user_input,
        **_runtime_chat_kwargs(
            runtime,
            chat_fn,
            request,
            user_id=user_id,
            big_session_id=big_session_id,
        ),
    )

    if isinstance(outcome, dict) and "answer" in outcome:
        answer = str(outcome.get("answer") or "")
        resolved_big = str(outcome.get("big_session_id") or big_session_id)
        resolved_small = str(outcome.get("small_session_id") or request.small_session_id or "")
        memory_md_path = str(outcome.get("memory_md_path") or "")
    else:
        answer = str(outcome or "")
        resolved_big = big_session_id
        resolved_small = request.small_session_id or ""
        memory_md_path = ""

    return WorkspaceChatResponse(
        answer=answer,
        workspace=str(workspace_dir),
        user_id=user_id,
        big_session_id=resolved_big,
        small_session_id=resolved_small,
        memory_md_path=memory_md_path,
    )


def _weixin_bridge_request(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    url = f"{WEIXIN_BRIDGE_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        detail: Any = raw or str(exc)
        try:
            parsed = json.loads(raw) if raw else {}
            detail = parsed.get("detail") or parsed
        except json.JSONDecodeError:
            pass
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Weixin bridge is unavailable at {WEIXIN_BRIDGE_URL}: {exc.reason}",
        ) from exc


def _weixin_bridge_is_healthy(timeout: float = 1.5) -> bool:
    try:
        request = urllib.request.Request(f"{WEIXIN_BRIDGE_URL}/health", method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _npm_executable() -> str:
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("npm executable was not found in PATH")


def _weixin_bridge_needs_build() -> bool:
    if not WEIXIN_BRIDGE_DIST.exists():
        return True
    if not WEIXIN_BRIDGE_SOURCE.exists():
        return False
    return WEIXIN_BRIDGE_SOURCE.stat().st_mtime > WEIXIN_BRIDGE_DIST.stat().st_mtime


def _ensure_weixin_bridge_built() -> None:
    if not WEIXIN_BRIDGE_AUTO_BUILD or not _weixin_bridge_needs_build():
        return
    if not WEIXIN_BRIDGE_ROOT.exists():
        raise RuntimeError(f"Weixin bridge project not found: {WEIXIN_BRIDGE_ROOT}")
    print("[orchestrator] building Weixin bridge...")
    subprocess.run(
        [_npm_executable(), "run", "build"],
        cwd=str(WEIXIN_BRIDGE_ROOT),
        check=True,
    )


def _start_weixin_bridge_process() -> None:
    global _WEIXIN_BRIDGE_PROCESS, _WEIXIN_BRIDGE_LOG_HANDLE
    if not WEIXIN_BRIDGE_AUTO_START:
        print("[orchestrator] Weixin bridge auto-start disabled")
        return
    if _weixin_bridge_is_healthy():
        print(f"[orchestrator] Weixin bridge already running at {WEIXIN_BRIDGE_URL}")
        return
    if _WEIXIN_BRIDGE_PROCESS and _WEIXIN_BRIDGE_PROCESS.poll() is None:
        return

    try:
        _ensure_weixin_bridge_built()
        WEIXIN_BRIDGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _WEIXIN_BRIDGE_LOG_HANDLE = WEIXIN_BRIDGE_LOG_PATH.open("a", encoding="utf-8")
        _WEIXIN_BRIDGE_LOG_HANDLE.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] starting Weixin bridge\n")
        _WEIXIN_BRIDGE_LOG_HANDLE.flush()

        env = os.environ.copy()
        env.setdefault("AGENT_ORCHESTRATOR_URL", "http://localhost:8001")
        _WEIXIN_BRIDGE_PROCESS = subprocess.Popen(
            [_npm_executable(), "run", "bridge"],
            cwd=str(WEIXIN_BRIDGE_ROOT),
            stdout=_WEIXIN_BRIDGE_LOG_HANDLE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        print(
            f"[orchestrator] started Weixin bridge pid={_WEIXIN_BRIDGE_PROCESS.pid} "
            f"log={WEIXIN_BRIDGE_LOG_PATH}"
        )
    except Exception as exc:
        print(f"[orchestrator] failed to start Weixin bridge: {exc}")


def _stop_weixin_bridge_process() -> None:
    global _WEIXIN_BRIDGE_PROCESS, _WEIXIN_BRIDGE_LOG_HANDLE
    process = _WEIXIN_BRIDGE_PROCESS
    _WEIXIN_BRIDGE_PROCESS = None
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        print("[orchestrator] stopped Weixin bridge")
    if _WEIXIN_BRIDGE_LOG_HANDLE:
        _WEIXIN_BRIDGE_LOG_HANDLE.close()
        _WEIXIN_BRIDGE_LOG_HANDLE = None


app = FastAPI(title="Agent Orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_weixin_bridge() -> None:
    _start_weixin_bridge_process()


@app.on_event("shutdown")
def shutdown_weixin_bridge() -> None:
    _stop_weixin_bridge_process()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=WorkspaceChatResponse)
def chat_endpoint(request: WorkspaceChatRequest) -> WorkspaceChatResponse:
    try:
        return run_workspace_chat(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/new-session", response_model=NewSessionResponse)
def new_session_endpoint(request: NewSessionRequest) -> NewSessionResponse:
    try:
        user_id = request.user_id or os.getenv("AGENT_DEFAULT_USER_ID", "ui_user")
        big_session_id = _allocate_big_session_id(None)
        return NewSessionResponse(big_session_id=big_session_id, user_id=user_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/weixin/login/start")
def weixin_login_start_endpoint(request: WeixinLoginStartRequest) -> Dict[str, Any]:
    try:
        workspace_dir = _resolve_workspace_dir(request.workspace)
        return _weixin_bridge_request(
            "POST",
            "/login/start",
            {"workspace": str(workspace_dir), "force": request.force},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/weixin/login/status")
def weixin_login_status_endpoint(sessionKey: str) -> Dict[str, Any]:
    if not sessionKey.strip():
        raise HTTPException(status_code=400, detail="sessionKey is required")
    query = urllib.parse.urlencode({"sessionKey": sessionKey})
    return _weixin_bridge_request("GET", f"/login/status?{query}", timeout=10.0)


@app.get("/weixin/accounts")
def weixin_accounts_endpoint() -> Dict[str, Any]:
    return _weixin_bridge_request("GET", "/accounts", timeout=10.0)


@app.post("/weixin/accounts/{account_id}/start")
def weixin_account_start_endpoint(account_id: str, request: WeixinAccountStartRequest) -> Dict[str, Any]:
    try:
        workspace_dir = _resolve_workspace_dir(request.workspace)
        safe_account = urllib.parse.quote(account_id, safe="")
        return _weixin_bridge_request(
            "POST",
            f"/accounts/{safe_account}/start",
            {"workspace": str(workspace_dir)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/weixin/accounts/{account_id}")
def weixin_account_delete_endpoint(account_id: str) -> Dict[str, Any]:
    safe_account = urllib.parse.quote(account_id, safe="")
    return _weixin_bridge_request("DELETE", f"/accounts/{safe_account}", timeout=20.0)

@app.post("/create-agent", response_model=BuildResponse)
def create_agent_endpoint(request: CreateAgentRequest) -> BuildResponse:
    try:
        return build_legacy_agent(request.agent_name, task=request.task, tools=request.tools)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/build-project", response_model=BuildResponse)
def build_project_endpoint(graph: GraphSpec) -> BuildResponse:
    try:
        return build_project_from_graph(graph)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _send_ws(websocket: WebSocket, message_type: str, payload: Dict[str, Any]) -> None:
    await websocket.send_text(json.dumps({"type": message_type, "payload": payload}, ensure_ascii=False))


@app.websocket("/ws/project-build")
async def project_build_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    graph: Optional[GraphSpec] = None
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_ws(websocket, "error", {"message": "invalid JSON message"})
                continue

            message_type = message.get("type")
            payload = message.get("payload") or {}
            if message_type == "graph.submit":
                try:
                    graph = GraphSpec.model_validate(payload)
                    plan = _build_plan_from_graph(graph)
                    await _send_ws(
                        websocket,
                        "graph.validated",
                        {
                            "projectName": plan.project_name,
                            "agentCount": len(plan.agent_specs),
                            "flowType": plan.flow_spec.flow_type if plan.flow_spec else "single",
                            "warnings": plan.warnings,
                        },
                    )
                except Exception as exc:
                    await _send_ws(websocket, "graph.invalid", {"error": str(exc)})
            elif message_type == "build.start":
                if graph is None:
                    await _send_ws(websocket, "build.failed", {"error": "graph has not been submitted"})
                    continue
                try:
                    await _send_ws(websocket, "build.started", {"message": "building workspace"})
                    result = build_project_from_graph(graph)
                    await _send_ws(websocket, "build.finished", _dump_model(result))
                except Exception as exc:
                    await _send_ws(websocket, "build.failed", {"error": str(exc)})
            else:
                await _send_ws(websocket, "error", {"message": f"unknown message type: {message_type}"})
    except WebSocketDisconnect:
        return

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an agent workspace from a graph spec.")
    parser.add_argument("--graph-json", help="Path to a GraphSpec JSON file.")
    parser.add_argument("--agent-name", help="Legacy single-agent build name.")
    parser.add_argument("--no-completion", action="store_true", help="Only generate skeleton files.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.graph_json:
        graph = GraphSpec.model_validate(json.loads(Path(args.graph_json).read_text(encoding="utf-8")))
        result = build_project_from_graph(graph, call_completion=not args.no_completion)
    elif args.agent_name:
        if args.no_completion:
            graph = GraphSpec(
                projectName=args.agent_name,
                nodes=[
                    GraphNode(id="user", type="user", label="User"),
                    GraphNode(id="agent", type="agent", label=args.agent_name, config={"name": args.agent_name}),
                ],
                edges=[GraphEdge(id="edge-1", source="user", target="agent")],
            )
            result = build_project_from_graph(graph, call_completion=False)
        else:
            result = build_legacy_agent(args.agent_name)
    else:
        raise SystemExit("Provide --graph-json or --agent-name")
    print(json.dumps(_dump_model(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
