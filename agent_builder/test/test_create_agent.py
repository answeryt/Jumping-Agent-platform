from __future__ import annotations

import importlib.util
from pathlib import Path


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

    def run(self, command: list, **kwargs) -> MockExecResult:  # noqa: ARG002
        if command[:2] == ["test", "-f"]:
            return MockExecResult(returncode=0 if command[2] in self.files else 1)
        return MockExecResult()

    def write_file(self, container_path: str, content: str) -> MockExecResult:
        self.files[container_path] = content
        return MockExecResult()


SCRIPT = Path(__file__).resolve().parent.parent / "agent_create" / "create_agent.py"
SPEC = importlib.util.spec_from_file_location("create_agent", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)

create_agent = MOD.create_agent
to_class_prefix = MOD.to_class_prefix


def test_to_class_prefix_simple() -> None:
    assert to_class_prefix("researcher", "agent") == "Researcher"


def test_to_class_prefix_numeric_name_is_safe() -> None:
    assert to_class_prefix("111", "agent") == "Agent111"


def test_create_agent_generates_files_with_safe_names() -> None:
    executor = MockExecutor()
    normalized = create_agent("111", executor=executor)
    assert normalized == "agent_111"
    assert "/workspace/Agent/agent_111_agent.py" in executor.files
    assert "/workspace/Prompt/agent_111_agent.md" in executor.files
    content = executor.files["/workspace/Agent/agent_111_agent.py"]
    assert "class Agent111Agent(BaseAgent)" in content
    assert 'agent_type="agent_111"' in content
    assert "def run(self, user_input: str, **kwargs: Any) -> str:" in content
    assert "model_kwargs = dict(kwargs)" in content
    assert 'model_kwargs.pop("history", None)' in content
    assert "self.model.chat_with_system(" in content

    prompt_content = executor.files["/workspace/Prompt/agent_111_agent.md"]
    assert "- `should_stop`: <true 或 false>" in prompt_content
    assert "不要额外输出 goal、user_request、known_info、phase、constraints、steps、skills_used、notes" in prompt_content
    assert "- `steps`:" not in prompt_content
    assert "- `skills_used`:" not in prompt_content
    assert "- `notes`:" not in prompt_content


def test_create_agent_does_not_overwrite_existing_files() -> None:
    executor = MockExecutor()
    executor.files["/workspace/Agent/reviewer_agent.py"] = "# sentinel"
    create_agent("reviewer", executor=executor)
    assert executor.files["/workspace/Agent/reviewer_agent.py"] == "# sentinel"



def test_runtime_template_does_not_forward_history_to_agents() -> None:
    runtime_template = Path(__file__).resolve().parent.parent / "run_time_templete" / "creat_runtime.py"
    content = runtime_template.read_text(encoding="utf-8")

    assert "merged_input = build_chat_input(user_input=user_input, history=history)" in content
    assert "reply = self.agent.run(merged_input)" in content
    assert "reply = self.agent.run(followup)" in content
    assert "self.agent.run(merged_input, history=history or [])" not in content
    assert "self.agent.run(followup, history=history or [])" not in content
