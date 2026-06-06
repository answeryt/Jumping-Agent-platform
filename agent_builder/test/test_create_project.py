from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_BUILDER = PROJECT_ROOT / "agent_builder"
sys.path.insert(0, str(AGENT_BUILDER))


class MockExecResult:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class MockExecutor:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.dirs: list[str] = []

    def run(self, command: list, workdir: str = "/workspace", timeout: int = 30) -> MockExecResult:  # noqa: ARG002
        if command[:2] == ["test", "-f"]:
            return MockExecResult(returncode=0 if command[2] in self.files else 1)
        if command[:2] == ["mkdir", "-p"]:
            self.dirs.append(command[2])
            return MockExecResult()
        return MockExecResult()

    def write_file(self, container_path: str, content: str) -> MockExecResult:
        self.files[container_path] = content
        return MockExecResult()


def _load_module(script_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, script_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module(AGENT_BUILDER / "project_create" / "creat_project.py", "creat_project")
create_project = _mod.create_project

_runtime_mod = _load_module(AGENT_BUILDER / "run_time_templete" / "creat_runtime.py", "creat_runtime")
runtime_files = _runtime_mod.runtime_files

_config_template_mod = _load_module(
    AGENT_BUILDER / "config_template" / "config_templete.py",
    "config_templete",
)
model_config_toml = _config_template_mod.model_config_toml


def test_create_project_creates_expected_directories() -> None:
    executor = MockExecutor()
    create_project("test_proj", executor=executor)
    for name in ["runtime"]:
        assert f"/workspace/test_proj/{name}" in executor.dirs
    assert "/workspace/test_proj/sandbox" not in executor.dirs
    for name in ["Agent", "Model", "Workflow", "Prompt", "Skill", "Config", "Test"]:
        assert f"/workspace/test_proj/runtime/{name}" in executor.dirs


def test_create_project_runtime_template_is_valid_python() -> None:
    runtime_content = runtime_files()["project_runtime.py"]
    compile(runtime_content, "project_runtime.py", "exec")
    assert "def _interactive_chat_loop() -> None:" in runtime_content
    assert 'user_input = input("You> ").strip()' in runtime_content

    base_agent_content = runtime_files()["Agent/base_agent.py"]
    compile(base_agent_content, "base_agent.py", "exec")
    assert "class PromptLoader:" in base_agent_content
    assert 'self.runtime_root = self.prompt_dir.parent.resolve()' in base_agent_content
    assert 'return self.prompt_loader.load(self.config.prompt_file, self.agent_type)' in base_agent_content
    assert "_build_runtime_context" not in base_agent_content
    assert "runtime tools are not mounted here" not in base_agent_content

    settings_content = runtime_files()["Config/settings.py"]
    compile(settings_content, "settings.py", "exec")
    assert "class LLMConfig:" in settings_content
    assert 'DEFAULT_MODEL_NAME = load_settings().llm_default.model' in settings_content

    model_content = runtime_files()["Model/openai_model.py"]
    compile(model_content, "openai_model.py", "exec")
    assert "from Config.settings import LLMConfig, load_settings" in model_content
    assert "client.chat.completions.create(" in model_content
    assert 'messages=[' in model_content
    assert 'stream=bool(kwargs.get("stream", self.stream))' in model_content


def test_generated_runtime_imports_without_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    for rel_path, content in runtime_files().items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    config_path = tmp_path / "Config" / "model_config.toml"
    config_path.write_text(model_config_toml(), encoding="utf-8")

    runtime_path = tmp_path / "project_runtime.py"
    spec = importlib.util.spec_from_file_location("_runtime_without_key", runtime_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    old_path = list(sys.path)
    old_modules = {
        key: sys.modules.get(key)
        for key in ("project_runtime", "Agent", "Model", "Workflow", "Config")
    }
    for key in list(sys.modules):
        if key in old_modules or key.startswith(("Agent.", "Model.", "Workflow.", "Config.")):
            sys.modules.pop(key, None)
    sys.path.insert(0, str(tmp_path))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
        for key in list(sys.modules):
            if key in old_modules or key.startswith(("Agent.", "Model.", "Workflow.", "Config.")):
                sys.modules.pop(key, None)
        for key, value in old_modules.items():
            if value is not None:
                sys.modules[key] = value

    assert hasattr(module, "chat")


def test_create_project_writes_runtime_base_files() -> None:
    executor = MockExecutor()
    create_project("test_proj", executor=executor)
    expected = [
        "/workspace/test_proj/runtime/.env",
        "/workspace/test_proj/runtime/project_runtime.py",
        "/workspace/test_proj/runtime/run_project.py",
        "/workspace/test_proj/runtime/Agent/base_agent.py",
        "/workspace/test_proj/runtime/Model/base_model.py",
        "/workspace/test_proj/runtime/Model/openai_model.py",
        "/workspace/test_proj/runtime/Workflow/base_flow.py",
        "/workspace/test_proj/runtime/Config/settings.py",
    ]
    for path in expected:
        assert path in executor.files, f"missing generated runtime file: {path}"
    content = executor.files["/workspace/test_proj/runtime/run_project.py"]
    assert "from project_runtime import main as run_cli" in content
    assert 'if __name__ == "__main__":' in content
    assert "run_cli()" in content

    runtime_content = executor.files["/workspace/test_proj/runtime/project_runtime.py"]
    assert "class RuntimeAgentRunner" in runtime_content
    assert 'RUNTIME_ROOT = Path(__file__).resolve().parent' in runtime_content
    assert "def _build_agent_runners(agents: Dict[str, BaseAgent]) -> Dict[str, RuntimeAgentRunner]:" in runtime_content
    assert "def _resolve_memory_context(" in runtime_content
    assert "flow = flow_cls(" in runtime_content
    assert "memory_context=memory_context" in runtime_content
    assert "history: Optional[List[Dict[str, str]]] = None" in runtime_content
    assert "history=history" in runtime_content
    assert "prompt_history = [" in runtime_content
    assert "reply = runner.run(user_input, history=prompt_history)" in runtime_content
    assert "memory.append(\"user\", user_input, agent_key=\"shared\")" in runtime_content
    assert "memory.append(\"assistant\", reply, agent_key=agent_name, turn_index=1)" in runtime_content
    assert "session_id=composite_session_id" not in runtime_content
    assert "small_session_id=resolved_small" not in runtime_content
    assert 'md_path=binding["md_path"]' not in runtime_content
    assert "build_plan.json is not valid JSON" in runtime_content
    assert "RuntimeToolExecutor" not in runtime_content
    assert "def _require_sandbox_base_urls(agent_names: List[str]) -> Dict[str, str]:" in runtime_content
    assert "build_plan.json marks sandbox agents but does not include sandbox endpoints for:" in runtime_content
    assert "require_agent_base_urls=True" in runtime_content

    workflow_content = executor.files["/workspace/test_proj/runtime/Workflow/base_flow.py"]
    assert "class AgentRunnerProtocol(Protocol):" in workflow_content
    assert "agent_runner = self.agents[agent_key]" in workflow_content


def test_create_project_does_not_overwrite_existing_file() -> None:
    executor = MockExecutor()
    executor.files["/workspace/test_proj/runtime/run_project.py"] = "# sentinel"
    create_project("test_proj", executor=executor)
    assert executor.files["/workspace/test_proj/runtime/run_project.py"] == "# sentinel"


def test_create_project_normalizes_spaces() -> None:
    executor = MockExecutor()
    result = create_project("my project", executor=executor)
    assert result == "/workspace/my_project"
