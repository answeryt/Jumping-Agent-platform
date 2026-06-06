from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.orchestrator import GraphEdge, GraphNode, GraphSpec, _build_plan_from_graph


def _agent_node(node_id: str, name: str) -> GraphNode:
    return GraphNode(
        id=node_id,
        type="agent",
        label=name,
        config={
            "name": name,
            "responsibility": f"Handle tasks for {name}.",
        },
    )


def _build_graph(agent_nodes: list[GraphNode], edges: list[GraphEdge]) -> GraphSpec:
    return GraphSpec(
        nodes=[GraphNode(id="user", type="user", label="User"), *agent_nodes],
        edges=edges,
    )


def test_graph_spec_accepts_frontend_flow_type_alias() -> None:
    graph = GraphSpec.model_validate(
        {
            "nodes": [
                {"id": "user", "type": "user", "label": "User"},
                {"id": "planner", "type": "agent", "label": "Planner", "config": {"name": "planner"}},
            ],
            "edges": [
                {
                    "id": "edge-1",
                    "source": "user",
                    "target": "planner",
                    "mode": "static",
                    "flowType": "debate",
                }
            ],
        }
    )

    assert graph.edges[0].flow_type == "debate"


def test_single_agent_graph_stays_single() -> None:
    graph = _build_graph(
        [_agent_node("solo", "solo")],
        [GraphEdge(id="edge-1", source="user", target="solo", mode="static")],
    )

    plan = _build_plan_from_graph(graph)

    assert plan.flow_spec is None


def test_sequential_graph_builds_sequential_flow() -> None:
    graph = _build_graph(
        [
            _agent_node("planner", "planner"),
            _agent_node("worker", "worker"),
            _agent_node("reviewer", "reviewer"),
        ],
        [
            GraphEdge(id="edge-1", source="user", target="planner", mode="static"),
            GraphEdge(id="edge-2", source="planner", target="worker", mode="static", flow_type="sequential"),
            GraphEdge(id="edge-3", source="worker", target="reviewer", mode="static", flow_type="sequential"),
        ],
    )

    plan = _build_plan_from_graph(graph)

    assert plan.flow_spec is not None
    assert plan.flow_spec.flow_type == "sequential"
    assert plan.flow_spec.filename == "Workflow/sequential_flow.py"


def test_router_graph_builds_router_flow() -> None:
    graph = _build_graph(
        [
            _agent_node("dispatcher", "dispatcher"),
            _agent_node("alpha", "alpha"),
            _agent_node("beta", "beta"),
        ],
        [
            GraphEdge(id="edge-1", source="user", target="dispatcher", mode="static"),
            GraphEdge(id="edge-2", source="dispatcher", target="alpha", mode="dynamic", flow_type="router"),
            GraphEdge(id="edge-3", source="dispatcher", target="beta", mode="dynamic", flow_type="router"),
        ],
    )

    plan = _build_plan_from_graph(graph)

    assert plan.flow_spec is not None
    assert plan.flow_spec.flow_type == "router"
    assert plan.flow_spec.details["dispatcher"] == "dispatcher"
    assert set(plan.flow_spec.details["branches"].values()) == {"alpha", "beta"}


def test_parallel_graph_builds_parallel_flow() -> None:
    graph = _build_graph(
        [
            _agent_node("dispatcher", "dispatcher"),
            _agent_node("worker_a", "worker_a"),
            _agent_node("worker_b", "worker_b"),
            _agent_node("aggregator", "aggregator"),
        ],
        [
            GraphEdge(id="edge-1", source="user", target="dispatcher", mode="static"),
            GraphEdge(id="edge-2", source="dispatcher", target="worker_a", mode="static", flow_type="parallel"),
            GraphEdge(id="edge-3", source="dispatcher", target="worker_b", mode="static", flow_type="parallel"),
            GraphEdge(id="edge-4", source="worker_a", target="aggregator", mode="static"),
            GraphEdge(id="edge-5", source="worker_b", target="aggregator", mode="static"),
        ],
    )

    plan = _build_plan_from_graph(graph)

    assert plan.flow_spec is not None
    assert plan.flow_spec.flow_type == "parallel"
    assert plan.flow_spec.details["dispatcher"] == "dispatcher"
    assert plan.flow_spec.details["aggregator"] == "aggregator"
    assert set(plan.flow_spec.details["workers"]) == {"worker_a", "worker_b"}


def test_parallel_graph_without_aggregator_keeps_all_workers() -> None:
    graph = _build_graph(
        [
            _agent_node("dispatcher", "dispatcher"),
            _agent_node("worker_a", "worker_a"),
            _agent_node("worker_b", "worker_b"),
        ],
        [
            GraphEdge(id="edge-1", source="dispatcher", target="worker_a", mode="static", flow_type="parallel"),
            GraphEdge(id="edge-2", source="dispatcher", target="worker_b", mode="static", flow_type="parallel"),
        ],
    )

    plan = _build_plan_from_graph(graph)

    assert plan.flow_spec is not None
    assert plan.flow_spec.flow_type == "parallel"
    assert plan.flow_spec.details["dispatcher"] == "dispatcher"
    assert plan.flow_spec.details["aggregator"] == "dispatcher"
    assert set(plan.flow_spec.details["workers"]) == {"worker_a", "worker_b"}


def test_loop_graph_builds_loop_flow() -> None:
    graph = _build_graph(
        [
            _agent_node("executor", "executor"),
            _agent_node("evaluator", "evaluator"),
        ],
        [
            GraphEdge(id="edge-1", source="user", target="executor", mode="static"),
            GraphEdge(id="edge-2", source="executor", target="evaluator", mode="static", flow_type="loop"),
            GraphEdge(id="edge-3", source="evaluator", target="executor", mode="static", flow_type="loop"),
        ],
    )

    plan = _build_plan_from_graph(graph)

    assert plan.flow_spec is not None
    assert plan.flow_spec.flow_type == "loop"
    assert plan.flow_spec.details == {"executor": "executor", "evaluator": "evaluator"}


def test_debate_graph_builds_debate_flow() -> None:
    graph = _build_graph(
        [
            _agent_node("participant_a", "participant_a"),
            _agent_node("participant_b", "participant_b"),
            _agent_node("moderator", "moderator"),
        ],
        [
            GraphEdge(id="edge-1", source="user", target="participant_a", mode="static"),
            GraphEdge(id="edge-2", source="participant_a", target="participant_b", mode="static", flow_type="debate"),
            GraphEdge(id="edge-3", source="participant_b", target="participant_a", mode="static", flow_type="debate"),
            GraphEdge(id="edge-4", source="participant_a", target="moderator", mode="static"),
            GraphEdge(id="edge-5", source="participant_b", target="moderator", mode="static"),
        ],
    )

    plan = _build_plan_from_graph(graph)

    assert plan.flow_spec is not None
    assert plan.flow_spec.flow_type == "debate"
    assert plan.flow_spec.details["moderator"] == "moderator"
    assert set(plan.flow_spec.details["participants"]) == {"participant_a", "participant_b"}


def test_hierarchical_graph_builds_hierarchical_flow() -> None:
    graph = _build_graph(
        [
            _agent_node("manager", "manager"),
            _agent_node("worker_a", "worker_a"),
            _agent_node("worker_b", "worker_b"),
        ],
        [
            GraphEdge(id="edge-1", source="user", target="manager", mode="static"),
            GraphEdge(id="edge-2", source="manager", target="worker_a", mode="dynamic", flow_type="hierarchical"),
            GraphEdge(id="edge-3", source="manager", target="worker_b", mode="dynamic", flow_type="hierarchical"),
        ],
    )

    plan = _build_plan_from_graph(graph)

    assert plan.flow_spec is not None
    assert plan.flow_spec.flow_type == "hierarchical"
    assert plan.flow_spec.details["manager"] == "manager"
    assert set(plan.flow_spec.details["workers"]) == {"worker_a", "worker_b"}
