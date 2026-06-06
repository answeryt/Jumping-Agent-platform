from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

import backend.orchestrator as orchestrator
from backend.sandbox_runtime import BackendSandboxRuntime


@dataclass(frozen=True)
class FakeSandboxInstance:
    agent_name: str
    base_url: str

    def model_dump(self) -> dict[str, str | int]:
        return {
            "agentName": self.agent_name,
            "containerName": f"container-{self.agent_name}",
            "hostPort": 18080,
            "sandboxUrl": self.base_url,
            "baseUrl": self.base_url,
            "mcpUrl": f"{self.base_url}/mcp",
            "dashboardUrl": f"{self.base_url}/index.html",
            "vncUrl": f"{self.base_url}/vnc/index.html?autoconnect=true",
        }


class FakeSandboxManager:
    def __init__(self) -> None:
        self.ensure_calls: list[tuple[str, list[tuple[str, str]]]] = []

    def ensure_agent_sandboxes(
        self,
        *,
        project_name: str,
        agents: list[tuple[str, str]],
    ) -> dict[str, FakeSandboxInstance]:
        self.ensure_calls.append((project_name, list(agents)))
        return {
            agent_name: FakeSandboxInstance(
                agent_name=agent_name,
                base_url=f"http://127.0.0.1:{18080 + index}",
            )
            for index, (_node_id, agent_name) in enumerate(agents)
        }


class FakeBackendSandboxRuntime:
    manager = FakeSandboxManager()


def _agent_node(node_id: str, name: str, *, sandbox: bool = False) -> orchestrator.GraphNode:
    config: dict[str, object] = {"name": name}
    if sandbox:
        config["capabilities"] = {"sandbox": {"enabled": True, "required": ["browser"]}}
    return orchestrator.GraphNode(id=node_id, type="agent", label=name, config=config)


def test_provision_backend_sandboxes_allocates_per_agent_instances(monkeypatch) -> None:
    fake_runtime = FakeBackendSandboxRuntime()
    monkeypatch.setattr(orchestrator, "BackendSandboxRuntime", lambda: fake_runtime)
    graph = orchestrator.GraphSpec(
        projectName="demo",
        nodes=[
            _agent_node("agent-a", "alpha", sandbox=True),
            _agent_node("agent-b", "beta", sandbox=True),
        ],
    )
    plan = orchestrator._build_plan_from_graph(graph)

    sandboxes = orchestrator._provision_backend_sandboxes(plan)

    assert fake_runtime.manager.ensure_calls == [
        ("demo", [("agent-a", "alpha"), ("agent-b", "beta")])
    ]
    assert set(sandboxes) == {"alpha", "beta"}
    assert sandboxes["alpha"]["baseUrl"] != sandboxes["beta"]["baseUrl"]


def test_resolve_workspace_sandboxes_returns_build_plan_metadata(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "demo"
    workspace.mkdir()
    (workspace / "project_runtime.py").write_text("# runtime", encoding="utf-8")
    metadata = {
        "alpha": {
            "agentName": "alpha",
            "baseUrl": "http://127.0.0.1:18080",
            "sandboxUrl": "http://127.0.0.1:18080",
        }
    }
    (workspace / "build_plan.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "agent_name": "alpha",
                        "sandbox_enabled": True,
                        "capabilities": {"sandbox": {"enabled": True}},
                    }
                ],
                "sandboxes": metadata,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(orchestrator, "WORKSPACE_ROOT", tmp_path)

    response = orchestrator.resolve_workspace_sandboxes(
        orchestrator.WorkspaceSandboxRequest(workspace="demo")
    )

    assert response.workspace == str(workspace.resolve())
    assert response.sandboxes == metadata


def test_build_plan_json_includes_sandbox_metadata() -> None:
    graph = orchestrator.GraphSpec(
        projectName="demo",
        nodes=[_agent_node("agent-a", "alpha", sandbox=True)],
    )
    plan = orchestrator._build_plan_from_graph(graph)
    metadata = {
        "alpha": {
            "agentName": "alpha",
            "baseUrl": "http://127.0.0.1:18080",
        }
    }

    payload = json.loads(orchestrator._build_plan_json(plan, sandboxes=metadata))

    assert payload["sandboxes"] == metadata


def test_resolve_workspace_sandboxes_fails_when_metadata_missing(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "demo"
    workspace.mkdir()
    (workspace / "project_runtime.py").write_text("# runtime", encoding="utf-8")
    (workspace / "build_plan.json").write_text(
        json.dumps(
            {
                "agents": [{"agent_name": "alpha", "sandbox_enabled": True}],
                "sandboxes": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(orchestrator, "WORKSPACE_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="does not include sandbox endpoints"):
        orchestrator.resolve_workspace_sandboxes(
            orchestrator.WorkspaceSandboxRequest(workspace="demo")
        )


def test_backend_sandbox_runtime_preserves_tool_catalog_errors(monkeypatch) -> None:
    runtime = BackendSandboxRuntime()
    monkeypatch.setattr(runtime, "list_servers", lambda agent_name: ["browser"])

    def _raise_list_tools(agent_name: str, server_name: str) -> dict[str, object]:
        raise RuntimeError("network down")

    monkeypatch.setattr(runtime, "list_tools", _raise_list_tools)

    with pytest.raises(RuntimeError, match="Failed to list MCP tools"):
        runtime.tool_catalog("alpha")


def test_backend_sandbox_runtime_can_require_recorded_agent_endpoint() -> None:
    runtime = BackendSandboxRuntime(require_agent_base_urls=True)

    with pytest.raises(RuntimeError, match="No sandbox endpoint recorded"):
        runtime.bind_existing("alpha")
