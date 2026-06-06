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


SCRIPT = Path(__file__).resolve().parent.parent / "config_creator" / "create_config.py"
SPEC = importlib.util.spec_from_file_location("create_config", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)

create_config = MOD.create_config


def test_create_config_generates_model_config() -> None:
    executor = MockExecutor()
    create_config("my project", executor=executor)

    path = "/workspace/my_project/runtime/Config/model_config.toml"
    assert path in executor.files
    assert '[llm.default]' in executor.files[path]
    assert 'api_key_env = "OPENAI_API_KEY"' in executor.files[path]


def test_create_config_does_not_overwrite_existing_file() -> None:
    executor = MockExecutor()
    path = "/workspace/my_project/runtime/Config/model_config.toml"
    executor.files[path] = "# sentinel"

    create_config("my project", executor=executor)

    assert executor.files[path] == "# sentinel"
