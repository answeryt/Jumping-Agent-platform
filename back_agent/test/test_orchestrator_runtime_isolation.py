from __future__ import annotations

import builtins
import sys
import threading
from pathlib import Path

import backend.orchestrator as orchestrator


RUNTIME_MODULE_ROOTS = ("project_runtime", "Agent", "Model", "Workflow", "Config", "Context")


def _runtime_module_names() -> set[str]:
    prefixes = tuple(f"{name}." for name in RUNTIME_MODULE_ROOTS)
    return {
        name
        for name in sys.modules
        if name in RUNTIME_MODULE_ROOTS or name.startswith(prefixes)
    }


def _restore_import_state(
    previous_sys_path: list[str],
    previous_modules: dict[str, object],
) -> None:
    for name in list(_runtime_module_names()):
        sys.modules.pop(name, None)
    sys.modules.update(previous_modules)
    sys.path[:] = previous_sys_path


def _write_workspace(workspace_dir: Path, runtime_source: str, marker: str) -> None:
    agent_dir = workspace_dir / "Agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "__init__.py").write_text("", encoding="utf-8")
    (agent_dir / "identity.py").write_text(f"NAME = {marker!r}\n", encoding="utf-8")
    (workspace_dir / "project_runtime.py").write_text(runtime_source, encoding="utf-8")


def test_load_workspace_runtime_restores_sys_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace_a"
    _write_workspace(
        workspace,
        "from Agent.identity import NAME\n",
        "workspace_a",
    )
    previous_sys_path = list(sys.path)
    previous_modules = {name: sys.modules[name] for name in _runtime_module_names()}

    try:
        module = orchestrator._load_workspace_runtime(workspace)

        assert module.NAME == "workspace_a"
        assert sys.path == previous_sys_path
    finally:
        _restore_import_state(previous_sys_path, previous_modules)


def test_concurrent_workspace_runtime_loads_do_not_share_runtime_modules(
    tmp_path: Path,
) -> None:
    workspace_a = tmp_path / "workspace_a"
    workspace_b = tmp_path / "workspace_b"
    started = threading.Event()
    builtins._orchestrator_runtime_isolation_started = started
    _write_workspace(
        workspace_a,
        "\n".join(
            [
                "import builtins",
                "import time",
                "builtins._orchestrator_runtime_isolation_started.set()",
                "time.sleep(0.15)",
                "from Agent.identity import NAME",
                "",
            ]
        ),
        "workspace_a",
    )
    _write_workspace(
        workspace_b,
        "\n".join(
            [
                "from Agent.identity import NAME",
                "",
            ]
        ),
        "workspace_b",
    )
    previous_sys_path = list(sys.path)
    previous_modules = {name: sys.modules[name] for name in _runtime_module_names()}
    results: dict[str, str] = {}
    errors: list[BaseException] = []

    def load_runtime(key: str, workspace: Path) -> None:
        try:
            results[key] = orchestrator._load_workspace_runtime(workspace).NAME
        except BaseException as exc:
            errors.append(exc)

    try:
        thread_a = threading.Thread(target=load_runtime, args=("a", workspace_a))
        thread_a.start()
        assert started.wait(2), "workspace_a did not start loading"
        thread_b = threading.Thread(target=load_runtime, args=("b", workspace_b))
        thread_b.start()
        thread_a.join(2)
        thread_b.join(2)

        assert not errors
        assert results == {"a": "workspace_a", "b": "workspace_b"}
        assert sys.path == previous_sys_path
    finally:
        thread_a.join(2)
        if "thread_b" in locals():
            thread_b.join(2)
        del builtins._orchestrator_runtime_isolation_started
        _restore_import_state(previous_sys_path, previous_modules)


def test_run_workspace_chat_restores_runtime_import_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "chat_workspace"
    _write_workspace(
        workspace,
        "\n".join(
            [
                "def chat(user_input: str):",
                "    from Agent.identity import NAME",
                "    return f'{NAME}:{user_input}'",
                "",
            ]
        ),
        "chat_workspace",
    )
    previous_sys_path = list(sys.path)
    previous_modules = {name: sys.modules[name] for name in _runtime_module_names()}
    monkeypatch.setattr(orchestrator, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(orchestrator, "_allocate_big_session_id", lambda existing: "big-session")

    try:
        response = orchestrator.run_workspace_chat(
            orchestrator.WorkspaceChatRequest(
                workspace="chat_workspace",
                user_input="hello",
            )
        )

        assert response.answer == "chat_workspace:hello"
        assert sys.path == previous_sys_path
        assert {
            name: sys.modules[name]
            for name in _runtime_module_names()
        } == previous_modules
    finally:
        _restore_import_state(previous_sys_path, previous_modules)
