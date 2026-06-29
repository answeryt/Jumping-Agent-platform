from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Iterator

os.environ.setdefault("WEIXIN_BRIDGE_AUTO_START", "0")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402
import uvicorn  # noqa: E402
import websockets  # noqa: E402

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


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int) -> None:
    import time

    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.02)
    raise RuntimeError("temporary uvicorn server did not start")


@pytest.fixture()
def uvicorn_server() -> Iterator[str]:
    port = _free_port()
    config = uvicorn.Config(orchestrator.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server(port)

    try:
        yield f"ws://127.0.0.1:{port}/ws/project-build"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_project_build_websocket_does_not_block_other_connections(
    monkeypatch: pytest.MonkeyPatch,
    uvicorn_server: str,
) -> None:
    build_entered = threading.Event()
    release_build = threading.Event()

    def blocking_build_project_from_graph(graph: GraphSpec) -> BuildResponse:
        build_entered.set()
        if not release_build.wait(timeout=5):
            raise RuntimeError("test build was not released")
        return BuildResponse(
            workspace="/tmp/fake-workspace",
            generated_files=[],
            answer="",
            project_name=graph.project_name,
            build_plan={},
        )

    monkeypatch.setattr(orchestrator, "build_project_from_graph", blocking_build_project_from_graph)

    async def run_check() -> None:
        async with websockets.connect(uvicorn_server) as slow_socket:
            async with websockets.connect(uvicorn_server) as other_socket:
                await slow_socket.send(
                    orchestrator.json.dumps(
                        {"type": "graph.submit", "payload": _valid_graph("slow_project")},
                        ensure_ascii=False,
                    )
                )
                assert orchestrator.json.loads(await slow_socket.recv())["type"] == "graph.validated"

                build_started = asyncio.Event()

                async def run_slow_build() -> None:
                    await slow_socket.send(
                        orchestrator.json.dumps({"type": "build.start", "payload": {}}, ensure_ascii=False)
                    )
                    first = orchestrator.json.loads(await slow_socket.recv())
                    assert first["type"] == "build.started"
                    build_started.set()
                    second = orchestrator.json.loads(await slow_socket.recv())
                    assert second["type"] == "build.finished"

                build_task = asyncio.create_task(run_slow_build())
                await asyncio.wait_for(build_started.wait(), timeout=2)
                assert await asyncio.to_thread(build_entered.wait, 2)

                try:
                    await other_socket.send(
                        orchestrator.json.dumps({"type": "unknown.message", "payload": {}}, ensure_ascii=False)
                    )
                    other_response = await asyncio.wait_for(other_socket.recv(), timeout=0.5)
                    assert orchestrator.json.loads(other_response)["type"] == "error"
                finally:
                    release_build.set()

                await asyncio.wait_for(build_task, timeout=2)

    asyncio.run(run_check())
