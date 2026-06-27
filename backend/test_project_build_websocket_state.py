from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("WEIXIN_BRIDGE_AUTO_START", "0")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend import orchestrator  # noqa: E402
from backend.orchestrator import BuildResponse, GraphSpec  # noqa: E402


def _valid_graph(project_name: str) -> dict[str, Any]:
    return {
        "projectName": project_name,
        "nodes": [
            {"id": "user", "type": "user", "label": "User"},
            {
                "id": "agent",
                "type": "agent",
                "label": "Agent",
                "config": {
                    "name": "agent",
                    "responsibility": "Complete the requested task.",
                },
            },
        ],
        "edges": [{"id": "edge-1", "source": "user", "target": "agent", "mode": "static"}],
    }


def test_project_build_websocket_invalid_resubmission_clears_previous_graph(monkeypatch: Any) -> None:
    built_projects: list[str] = []

    def fake_build_project_from_graph(graph: GraphSpec) -> BuildResponse:
        built_projects.append(graph.project_name)
        return BuildResponse(
            workspace="/tmp/fake-workspace",
            generated_files=[],
            answer="",
            project_name=graph.project_name,
            build_plan={},
        )

    monkeypatch.setattr(orchestrator, "build_project_from_graph", fake_build_project_from_graph)

    with TestClient(orchestrator.app) as client:
        with client.websocket_connect("/ws/project-build") as websocket:
            websocket.send_json({"type": "graph.submit", "payload": _valid_graph("first_project")})
            assert websocket.receive_json()["type"] == "graph.validated"

            websocket.send_json(
                {
                    "type": "graph.submit",
                    "payload": {
                        "projectName": "second_project",
                        "nodes": [{"id": "user"}],
                        "edges": [],
                    },
                }
            )
            assert websocket.receive_json()["type"] == "graph.invalid"

            websocket.send_json({"type": "build.start", "payload": {}})
            message = websocket.receive_json()

    assert message["type"] == "build.failed"
    assert message["payload"]["error"] == "graph has not been submitted"
    assert built_projects == []


def test_project_build_websocket_graph_state_is_connection_local(monkeypatch: Any) -> None:
    built_projects: list[str] = []

    def fake_build_project_from_graph(graph: GraphSpec) -> BuildResponse:
        built_projects.append(graph.project_name)
        return BuildResponse(
            workspace="/tmp/fake-workspace",
            generated_files=[],
            answer="",
            project_name=graph.project_name,
            build_plan={},
        )

    monkeypatch.setattr(orchestrator, "build_project_from_graph", fake_build_project_from_graph)

    with TestClient(orchestrator.app) as client:
        with client.websocket_connect("/ws/project-build") as first_socket:
            first_socket.send_json({"type": "graph.submit", "payload": _valid_graph("first_project")})
            assert first_socket.receive_json()["type"] == "graph.validated"

            with client.websocket_connect("/ws/project-build") as second_socket:
                second_socket.send_json({"type": "build.start", "payload": {}})
                second_message = second_socket.receive_json()

            first_socket.send_json({"type": "build.start", "payload": {}})
            first_started = first_socket.receive_json()
            first_finished = first_socket.receive_json()

    assert second_message["type"] == "build.failed"
    assert second_message["payload"]["error"] == "graph has not been submitted"
    assert first_started["type"] == "build.started"
    assert first_finished["type"] == "build.finished"
    assert built_projects == ["first_project"]
