from __future__ import annotations

from fastapi.testclient import TestClient

import backend.orchestrator as orchestrator


def _valid_graph_payload(project_name: str = "demo") -> dict[str, object]:
    return {
        "projectName": project_name,
        "nodes": [
            {
                "id": "agent-a",
                "type": "agent",
                "label": "Alpha",
                "config": {"name": "alpha"},
            }
        ],
        "edges": [],
    }


def test_project_build_websocket_clears_graph_after_invalid_resubmission(monkeypatch) -> None:
    built_graphs: list[orchestrator.GraphSpec] = []

    def _build_project_from_graph(graph: orchestrator.GraphSpec) -> orchestrator.BuildResponse:
        built_graphs.append(graph)
        return orchestrator.BuildResponse(
            workspace="/tmp/demo",
            generated_files=[],
            answer="",
            project_name=graph.project_name,
            build_plan={},
            sandboxes={},
        )

    monkeypatch.setattr(orchestrator, "build_project_from_graph", _build_project_from_graph)
    client = TestClient(orchestrator.app)

    with client.websocket_connect("/ws/project-build") as websocket:
        websocket.send_json({"type": "graph.submit", "payload": _valid_graph_payload("first")})
        assert websocket.receive_json()["type"] == "graph.validated"

        websocket.send_json(
            {
                "type": "graph.submit",
                "payload": {
                    "projectName": "second",
                    "nodes": [{"id": "agent-b"}],
                },
            }
        )
        assert websocket.receive_json()["type"] == "graph.invalid"

        websocket.send_json({"type": "build.start", "payload": {}})
        response = websocket.receive_json()

    assert response == {
        "type": "build.failed",
        "payload": {"error": "graph has not been submitted"},
    }
    assert built_graphs == []


def test_project_build_websocket_still_builds_after_valid_submission(monkeypatch) -> None:
    built_graphs: list[orchestrator.GraphSpec] = []

    def _build_project_from_graph(graph: orchestrator.GraphSpec) -> orchestrator.BuildResponse:
        built_graphs.append(graph)
        return orchestrator.BuildResponse(
            workspace="/tmp/demo",
            generated_files=["project_runtime.py"],
            answer="done",
            project_name=graph.project_name,
            build_plan={"project_name": graph.project_name},
            sandboxes={},
        )

    monkeypatch.setattr(orchestrator, "build_project_from_graph", _build_project_from_graph)
    client = TestClient(orchestrator.app)

    with client.websocket_connect("/ws/project-build") as websocket:
        websocket.send_json({"type": "graph.submit", "payload": _valid_graph_payload("fresh")})
        assert websocket.receive_json()["type"] == "graph.validated"

        websocket.send_json({"type": "build.start", "payload": {}})
        assert websocket.receive_json()["type"] == "build.started"
        response = websocket.receive_json()

    assert response["type"] == "build.finished"
    assert response["payload"]["project_name"] == "fresh"
    assert [graph.project_name for graph in built_graphs] == ["fresh"]
