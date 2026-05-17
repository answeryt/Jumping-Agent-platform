from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.orchestrator import (
    AgentBuildSpec,
    AgentNodeConfig,
    BuildPlan,
    FlowBuildSpec,
    ProjectPaths,
    GraphEdge,
    GraphNode,
    GraphSpec,
    _build_workspace_completion_task,
    _build_legacy_completion_task,
)


def _sample_plan() -> tuple[BuildPlan, AgentBuildSpec, dict[str, str]]:
    config = AgentNodeConfig(
        name="planner",
        responsibility="Plan the user's task and hand off implementation work when needed.",
        deliverable="plan",
        modelProfile="balanced",
        autonomy="structured",
        guidance="Keep answers practical.",
        tools=[],
    )
    worker_config = AgentNodeConfig(name="worker", responsibility="Implement the task.")
    graph = GraphSpec(
        nodes=[
            GraphNode(id="user", type="user", label="User"),
            GraphNode(id="planner-node", type="agent", label="Planner", config=config.model_dump()),
            GraphNode(
                id="worker-node",
                type="agent",
                label="Worker",
                config=worker_config.model_dump(),
            ),
        ],
        edges=[
            GraphEdge(id="edge-1", source="user", target="planner-node", mode="static"),
            GraphEdge(id="edge-2", source="planner-node", target="worker-node", mode="static"),
        ],
    )
    agent_spec = AgentBuildSpec(
        node_id="planner-node",
        agent_name="planner",
        label="Planner",
        config=config,
        tool_scaffolds=[],
        upstream_nodes=["user"],
        static_downstream_agents=["worker-node"],
        dynamic_downstream_agents=[],
    )
    plan = BuildPlan(
        project_name="demo",
        graph=graph,
        agent_specs=[agent_spec],
        flow_spec=FlowBuildSpec(
            flow_type="sequential",
            filename="Workflow/sequential_flow.py",
            details={"order": ["planner", "worker"]},
        ),
        warnings=[],
    )
    agent_names_by_id = {"planner-node": "planner", "worker-node": "worker", "user": "user"}
    return plan, agent_spec, agent_names_by_id


def test_build_workspace_completion_task_mentions_framework_contract_requirements() -> None:
    plan, _agent_spec, agent_names_by_id = _sample_plan()

    prompt = _build_workspace_completion_task(
        plan=plan,
        paths=ProjectPaths(
            project_root=Path("/tmp/demo"),
            runtime_root=Path("/tmp/demo/runtime"),
            sandbox_root=Path("/tmp/demo/sandbox"),
        ),
        agent_names_by_id=agent_names_by_id,
    )

    assert "Treat the whole generated runtime as the unit of completion" in prompt
    assert "Do not stop after completing only one agent file" in prompt
    assert "First identify the runtime's agent framework contract" in prompt
    assert "Keep all generated files compatible with that framework contract" in prompt
    assert "In multi-agent workspaces, express role differences through prompt, schema, flow, and handoff behavior" in prompt
    assert "do not leave it in a half-implemented state" in prompt
    assert "Do not express role differences by omitting a required framework entrypoint" in prompt
    assert "Sandbox directory: /tmp/demo/sandbox" in prompt


def test_build_legacy_completion_task_mentions_framework_contract_requirements() -> None:
    prompt = _build_legacy_completion_task(
        agent_name="greeter",
        tool_names=["search"],
        paths=ProjectPaths(
            project_root=Path("/tmp/greeter"),
            runtime_root=Path("/tmp/greeter/runtime"),
            sandbox_root=Path("/tmp/greeter/sandbox"),
        ),
    )

    assert "First identify the runtime's agent framework contract" in prompt
    assert "Keep the generated files compatible with that contract" in prompt
    assert "If a generated node will be discovered or executed by the current framework, do not leave it half-implemented" in prompt
