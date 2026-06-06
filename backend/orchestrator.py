from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import sys
import time
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Literal, Optional

import asyncio
import queue

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = BACKEND_ROOT / "workspace"
AGENT_BUILDER_ROOT = PROJECT_ROOT / "agent_builder"
BACK_AGENT_API_URL = os.getenv("REACT_AGENT_API_URL", "http://localhost:8000/chat")
_WORKSPACE_RUNTIME_MODULE_ROOTS = (
    "project_runtime",
    "Agent",
    "Model",
    "Workflow",
    "Config",
    "Context",
)
_WORKSPACE_RUNTIME_MODULE_PREFIXES = tuple(
    f"{name}." for name in _WORKSPACE_RUNTIME_MODULE_ROOTS
)
_WORKSPACE_RUNTIME_IMPORT_LOCK = threading.RLock()

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
from sandbox_runtime import (
    BackendSandboxRuntime,
    recent_tool_events,
    register_tool_trace_listener,
)


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
    sandbox: bool = False


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
    sandbox_root: Optional[Path] = None


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
    sandboxes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class SandboxPromptResponse(BaseModel):
    agent_name: str
    prompt: str
    sandbox: Dict[str, Any]


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


class WorkspaceSandboxRequest(BaseModel):
    workspace: Optional[str] = None


class WorkspaceSandboxResponse(BaseModel):
    workspace: str
    sandboxes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


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


SANDBOX_CAPABILITIES = {"browser", "vscode", "jupyter"}
SANDBOX_ENABLE_MARKERS = {"sandbox", "aio_sandbox", "mcp"}


def _sandbox_capability_name(value: Any) -> Optional[str]:
    name = str(value or "").strip().lower()
    return name if name in SANDBOX_CAPABILITIES else None


def _add_sandbox_capability(capabilities: List[str], value: Any) -> None:
    name = _sandbox_capability_name(value)
    if name and name not in capabilities:
        capabilities.append(name)


def _collect_sandbox_capability_request(value: Any) -> tuple[bool, List[str]]:
    enabled = False
    capabilities: List[str] = []
    if value is True:
        return True, capabilities
    if isinstance(value, str):
        _add_sandbox_capability(capabilities, value)
        return value.strip().lower() in SANDBOX_ENABLE_MARKERS or bool(capabilities), capabilities
    if isinstance(value, (list, tuple, set)):
        for item in value:
            item_enabled, item_capabilities = _collect_sandbox_capability_request(item)
            enabled = enabled or item_enabled
            for capability in item_capabilities:
                _add_sandbox_capability(capabilities, capability)
        return enabled, capabilities
    if isinstance(value, dict):
        enabled = value.get("enabled") is True
        for key in ("capability", "name", "id", "type"):
            _add_sandbox_capability(capabilities, value.get(key))
        for key in ("required", "requires", "capabilities", "tools", "needs"):
            item_enabled, item_capabilities = _collect_sandbox_capability_request(value.get(key))
            enabled = enabled or item_enabled
            for capability in item_capabilities:
                _add_sandbox_capability(capabilities, capability)
        return enabled or bool(capabilities), capabilities
    return False, capabilities


def _merge_sandbox_capability_config(
    capabilities: Dict[str, Any],
    *,
    enabled: bool,
    required: List[str],
) -> Dict[str, Any]:
    if not enabled and not required:
        return capabilities
    merged = dict(capabilities)
    current = merged.get("sandbox")
    sandbox_config = dict(current) if isinstance(current, dict) else {}
    sandbox_config["enabled"] = True
    existing_required = sandbox_config.get("required")
    _existing_enabled, existing_capabilities = _collect_sandbox_capability_request(existing_required)
    del _existing_enabled
    combined: List[str] = []
    for capability in [*existing_capabilities, *required]:
        _add_sandbox_capability(combined, capability)
    if combined:
        sandbox_config["required"] = combined
    else:
        sandbox_config.pop("required", None)
    merged["sandbox"] = sandbox_config
    return merged


def _normalize_agent_config_payload(config_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(config_payload)
    raw_capabilities = payload.get("capabilities") or {}
    capabilities = dict(raw_capabilities) if isinstance(raw_capabilities, dict) else {}
    sandbox_enabled, requested = _collect_sandbox_capability_request(capabilities.get("sandbox"))
    sandbox_enabled = sandbox_enabled or payload.get("sandbox") is True

    normalized_tools: List[Any] = []
    for tool in payload.get("tools") or []:
        if isinstance(tool, dict):
            tool_capabilities: List[str] = []
            for key in ("capability", "name", "id", "type"):
                _add_sandbox_capability(tool_capabilities, tool.get(key))
            marker = str(tool.get("type") or tool.get("name") or tool.get("id") or "").strip().lower()
            if tool_capabilities or marker in SANDBOX_ENABLE_MARKERS:
                sandbox_enabled = True
                for capability in tool_capabilities:
                    _add_sandbox_capability(requested, capability)
                continue
            normalized_tools.append(
                {
                    key: value
                    for key, value in tool.items()
                    if key not in {"server", "server_name", "tool", "tool_name"}
                }
            )
            continue

        capability = _sandbox_capability_name(tool)
        marker = str(tool or "").strip().lower()
        if capability or marker in SANDBOX_ENABLE_MARKERS:
            sandbox_enabled = True
            _add_sandbox_capability(requested, capability)
            continue
        normalized_tools.append(tool)

    payload["tools"] = normalized_tools
    payload["capabilities"] = _merge_sandbox_capability_config(
        capabilities,
        enabled=sandbox_enabled,
        required=requested,
    )
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
    aggregator_id = max(downstream_counts, key=downstream_counts.get) if downstream_counts else dispatcher_id
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
    if not agent_specs:
        warnings.append("graph has no agent nodes")
    return BuildPlan(
        project_name=normalize_python_name(graph.project_name or graph.project_id or "agent_project", "project"),
        graph=graph,
        agent_specs=agent_specs,
        flow_spec=flow_spec,
        warnings=warnings,
    )


def _config_requests_sandbox(config: AgentNodeConfig) -> bool:
    if config.sandbox:
        return True
    sandbox_enabled, sandbox_capabilities = _collect_sandbox_capability_request(
        config.capabilities.get("sandbox")
    )
    if sandbox_enabled or sandbox_capabilities:
        return True
    for item in config.tools:
        if isinstance(item, dict):
            values = [item.get("capability"), item.get("name"), item.get("type"), item.get("id")]
        else:
            values = [item]
        if any(
            str(value).strip().lower() in SANDBOX_ENABLE_MARKERS or _sandbox_capability_name(value)
            for value in values
            if value
        ):
            return True
    return False


def _sandbox_capability_summaries(config: AgentNodeConfig) -> List[str]:
    _enabled, requested = _collect_sandbox_capability_request(config.capabilities.get("sandbox"))
    del _enabled
    for tool in config.tools:
        if isinstance(tool, dict):
            for key in ("capability", "name", "id", "type"):
                _add_sandbox_capability(requested, tool.get(key))
        else:
            _add_sandbox_capability(requested, tool)
    labels = {
        "browser": "browser capability",
        "vscode": "VS Code capability",
        "jupyter": "Jupyter capability",
    }
    return [labels.get(capability, f"{capability} capability") for capability in requested]


def _provision_backend_sandboxes(plan: BuildPlan) -> Dict[str, Dict[str, Any]]:
    runtime = BackendSandboxRuntime()
    sandbox_agents = [
        (spec.node_id, spec.agent_name)
        for spec in plan.agent_specs
        if _config_requests_sandbox(spec.config)
    ]
    if not sandbox_agents:
        return {}

    instances = runtime.manager.ensure_agent_sandboxes(
        project_name=plan.project_name,
        agents=sandbox_agents,
    )
    return {
        agent_name: instance.model_dump()
        for agent_name, instance in instances.items()
    }


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
    sandbox_capability_summaries = _sandbox_capability_summaries(spec.config)
    if _config_requests_sandbox(spec.config):
        additions.extend(
            [
                "",
                "## Sandbox Capabilities",
                "- This agent may use the mounted sandbox MCP environment for declared capabilities only.",
                "- Do not invent MCP server or tool names from this static prompt.",
                "- The backend injects the live MCP server/tool catalog at runtime; use only names from that dynamic catalog.",
            ]
        )
        if sandbox_capability_summaries:
            additions.extend(f"- {summary}" for summary in sandbox_capability_summaries)
        else:
            additions.append("- sandbox capability")
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


def _build_plan_json(
    plan: BuildPlan,
    *,
    sandboxes: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
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
                "sandbox": spec.config.sandbox,
                "sandbox_enabled": _config_requests_sandbox(spec.config),
                "upstream_nodes": spec.upstream_nodes,
                "static_downstream_agents": spec.static_downstream_agents,
                "dynamic_downstream_agents": spec.dynamic_downstream_agents,
            }
            for spec in plan.agent_specs
        ],
        "warnings": plan.warnings,
        "sandboxes": sandboxes or {},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _generate_workspace(
    plan: BuildPlan,
    *,
    sandboxes: Optional[Dict[str, Dict[str, Any]]] = None,
) -> tuple[ProjectPaths, List[str], Dict[str, str]]:
    project_root = _safe_project_dir(plan.project_name)
    runtime_root = project_root
    generated: List[str] = []

    for directory in RUNTIME_PROJECT_DIRS:
        (runtime_root / directory).mkdir(parents=True, exist_ok=True)

    for rel_path, content in {**RUNTIME_PROJECT_FILES, **runtime_files()}.items():
        _write_text(runtime_root / rel_path, content, generated, runtime_root)
    _write_text(runtime_root / "Config" / "model_config.toml", model_config_toml(), generated, runtime_root)

    agent_names_by_id = _agent_name_map(plan.graph)
    for spec in plan.agent_specs:
        class_prefix = to_class_prefix(spec.agent_name, "agent")
        prompt_file = f"{spec.agent_name}_agent.md"
        _write_text(runtime_root / "Agent" / f"{spec.agent_name}_agent.py", agent_py(class_prefix, spec.agent_name, prompt_file), generated, runtime_root)
        _write_text(runtime_root / "Prompt" / prompt_file, _prompt_for_agent(spec, plan), generated, runtime_root)

    if plan.flow_spec is not None:
        _write_text(runtime_root / plan.flow_spec.filename, _flow_source(plan.flow_spec), generated, runtime_root)

    _write_text(
        runtime_root / "build_plan.json",
        _build_plan_json(plan, sandboxes=sandboxes),
        generated,
        runtime_root,
    )
    return ProjectPaths(project_root=project_root, runtime_root=runtime_root), generated, agent_names_by_id


def _build_workspace_completion_task(plan: BuildPlan, paths: ProjectPaths, agent_names_by_id: Dict[str, str]) -> str:
    flow_type = plan.flow_spec.flow_type if plan.flow_spec else "single"
    skill = "multi-agent-skill" if len(plan.agent_specs) > 1 else "single-agent-skill"
    agents = "\n".join(
        f"- {spec.agent_name}: {spec.config.responsibility or spec.label}"
        for spec in plan.agent_specs
    )
    sandbox_agents = "\n".join(
        f"- {spec.agent_name}: {', '.join(_sandbox_capability_summaries(spec.config)) or 'sandbox capability'}"
        for spec in plan.agent_specs
        if _config_requests_sandbox(spec.config)
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
Sandbox directory: {paths.sandbox_root.as_posix() if paths.sandbox_root else "none"}
Flow type: {flow_type}

Generated agents:
{agents or "- none"}

Sandbox MCP agents:
{sandbox_agents or "- none"}

Flow details:
{json.dumps(flow_details, ensure_ascii=False, indent=2)}

Node id to agent name mapping:
{json.dumps(agent_names_by_id, ensure_ascii=False, indent=2)}

Task:
1. Call load_project on the workspace directory.
2. Inspect the generated runtime contract before editing.
3. Complete the generated Agent and Prompt files, and update flow/runtime files only if needed for compatibility.
   If build_plan.json marks any agent with sandbox_enabled or sandbox capabilities, preserve the backend-owned MCP contract: load BackendSandboxRuntime context for that agent and execute JSON sandbox_tool_call requests through the backend adapter using only the injected live catalog.
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

    sandboxes = _provision_backend_sandboxes(plan)
    paths, generated_files, agent_names_by_id = _generate_workspace(
        plan,
        sandboxes=sandboxes,
    )
    answer = ""
    if call_completion:
        task = _build_workspace_completion_task(plan=plan, paths=paths, agent_names_by_id=agent_names_by_id)
        answer = _call_back_agent(task)
    return BuildResponse(
        workspace=str(paths.runtime_root),
        generated_files=sorted(generated_files),
        answer=answer,
        project_name=paths.project_root.name,
        build_plan=json.loads(_build_plan_json(plan, sandboxes=sandboxes)),
        sandboxes=sandboxes,
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
    sandboxes = _provision_backend_sandboxes(plan)
    paths, generated_files, _agent_names_by_id = _generate_workspace(
        plan,
        sandboxes=sandboxes,
    )
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
        build_plan=json.loads(_build_plan_json(plan, sandboxes=sandboxes)),
        sandboxes=sandboxes,
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


def _is_workspace_runtime_module(module_name: str) -> bool:
    return (
        module_name in _WORKSPACE_RUNTIME_MODULE_ROOTS
        or module_name.startswith(_WORKSPACE_RUNTIME_MODULE_PREFIXES)
    )


def _snapshot_workspace_runtime_modules() -> Dict[str, Any]:
    return {
        name: module
        for name, module in sys.modules.items()
        if _is_workspace_runtime_module(name)
    }


def _clear_workspace_runtime_modules() -> None:
    for name in list(sys.modules):
        if _is_workspace_runtime_module(name):
            sys.modules.pop(name, None)


@contextmanager
def _workspace_runtime_import_state(workspace_dir: Path) -> Iterator[None]:
    workspace_path = str(workspace_dir)
    with _WORKSPACE_RUNTIME_IMPORT_LOCK:
        previous_sys_path = list(sys.path)
        previous_modules = _snapshot_workspace_runtime_modules()
        try:
            _clear_workspace_runtime_modules()
            sys.path[:] = [path for path in sys.path if path != workspace_path]
            sys.path.insert(0, workspace_path)
            yield
        finally:
            _clear_workspace_runtime_modules()
            sys.modules.update(previous_modules)
            sys.path[:] = previous_sys_path


def _load_workspace_runtime_module(workspace_dir: Path) -> Any:
    runtime_path = workspace_dir / "project_runtime.py"
    module_name = f"_workspace_project_runtime_{abs(hash(str(workspace_dir)))}_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(module_name, runtime_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 workspace runtime: {runtime_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_workspace_runtime(workspace_dir: Path) -> Any:
    with _workspace_runtime_import_state(workspace_dir):
        return _load_workspace_runtime_module(workspace_dir)


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
    with _workspace_runtime_import_state(workspace_dir):
        runtime = _load_workspace_runtime_module(workspace_dir)
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


def _sandbox_agent_names_from_build_plan(workspace_dir: Path) -> List[str]:
    build_plan_path = workspace_dir / "build_plan.json"
    if not build_plan_path.exists():
        return []
    payload = json.loads(build_plan_path.read_text(encoding="utf-8"))
    names: List[str] = []
    for agent in payload.get("agents", []):
        agent_name = str(agent.get("agent_name", "")).strip()
        if not agent_name:
            continue
        capabilities = agent.get("capabilities") or {}
        sandbox_capability = capabilities.get("sandbox") if isinstance(capabilities, dict) else None
        sandbox_enabled, sandbox_capabilities = _collect_sandbox_capability_request(sandbox_capability)
        if bool(
            agent.get("sandbox_enabled")
            or agent.get("sandbox")
            or sandbox_enabled
            or sandbox_capabilities
        ):
            names.append(agent_name)
    return names


def _sandbox_metadata_from_build_plan(workspace_dir: Path) -> Dict[str, Dict[str, Any]]:
    build_plan_path = workspace_dir / "build_plan.json"
    if not build_plan_path.exists():
        return {}
    payload = json.loads(build_plan_path.read_text(encoding="utf-8"))
    sandboxes = payload.get("sandboxes") or {}
    if not isinstance(sandboxes, dict):
        return {}
    return {
        str(agent_name): dict(metadata)
        for agent_name, metadata in sandboxes.items()
        if isinstance(metadata, dict)
    }


def resolve_workspace_sandboxes(request: WorkspaceSandboxRequest) -> WorkspaceSandboxResponse:
    workspace_dir = _resolve_workspace_dir(request.workspace)
    sandboxes = _sandbox_metadata_from_build_plan(workspace_dir)
    missing_agents = [
        agent_name
        for agent_name in _sandbox_agent_names_from_build_plan(workspace_dir)
        if agent_name not in sandboxes
    ]
    if missing_agents:
        raise RuntimeError(
            "build_plan.json marks sandbox agents but does not include sandbox endpoints for: "
            + ", ".join(sorted(missing_agents))
        )
    return WorkspaceSandboxResponse(workspace=str(workspace_dir), sandboxes=sandboxes)


def _workspace_http_exception(exc: Exception) -> HTTPException:
    raw = str(exc)
    if isinstance(exc, FileNotFoundError):
        if "backend/workspace" in raw:
            detail = "No runnable agent workspace found in backend/workspace"
        elif "workspace" in raw:
            detail = "workspace is not runnable or does not exist"
        else:
            detail = raw or "file not found"
        return HTTPException(status_code=404, detail=detail)
    if isinstance(exc, ValueError) and "workspace" in raw:
        return HTTPException(status_code=400, detail="workspace must be inside backend/workspace")
    if "workspace runtime" in raw:
        return HTTPException(status_code=500, detail=raw)
    return HTTPException(status_code=500, detail=raw)


app = FastAPI(title="Agent Orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=WorkspaceChatResponse)
def chat_endpoint(request: WorkspaceChatRequest) -> WorkspaceChatResponse:
    try:
        return run_workspace_chat(request)
    except Exception as exc:
        raise _workspace_http_exception(exc) from exc


@app.post("/new-session", response_model=NewSessionResponse)
def new_session_endpoint(request: NewSessionRequest) -> NewSessionResponse:
    try:
        user_id = request.user_id or os.getenv("AGENT_DEFAULT_USER_ID", "ui_user")
        big_session_id = _allocate_big_session_id(None)
        return NewSessionResponse(big_session_id=big_session_id, user_id=user_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/sandbox/events/recent")
def sandbox_events_recent(limit: int = 50) -> Dict[str, Any]:
    return {"events": recent_tool_events(limit=max(1, min(int(limit or 50), 200)))}


@app.get("/sandbox/events/stream")
async def sandbox_events_stream() -> StreamingResponse:
    event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()

    def _on_event(event: Any) -> None:
        try:
            event_queue.put_nowait(event.to_dict())
        except Exception:
            pass

    unsubscribe = register_tool_trace_listener(_on_event)

    async def _iter() -> Any:
        try:
            for event in recent_tool_events(limit=20):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            while True:
                try:
                    event = await asyncio.get_event_loop().run_in_executor(
                        None, event_queue.get, True, 15
                    )
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            return
        finally:
            unsubscribe()

    return StreamingResponse(_iter(), media_type="text/event-stream")


@app.post("/workspace-sandboxes", response_model=WorkspaceSandboxResponse)
def workspace_sandboxes_endpoint(request: WorkspaceSandboxRequest) -> WorkspaceSandboxResponse:
    try:
        return resolve_workspace_sandboxes(request)
    except Exception as exc:
        raise _workspace_http_exception(exc) from exc


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


@app.get("/sandbox/{agent_name}/prompt", response_model=SandboxPromptResponse)
def sandbox_prompt_endpoint(agent_name: str) -> SandboxPromptResponse:
    try:
        runtime = BackendSandboxRuntime()
        instance = runtime.instance(agent_name)
        return SandboxPromptResponse(
            agent_name=agent_name,
            prompt=runtime.prompt_for_agent(agent_name),
            sandbox=instance.model_dump(),
        )
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
                graph = None
                try:
                    submitted_graph = GraphSpec.model_validate(payload)
                    plan = _build_plan_from_graph(submitted_graph)
                    graph = submitted_graph
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
