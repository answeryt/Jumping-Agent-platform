"""
test_create_project.py

测试 agent_builder/project_create/creat_project.py 在沙盒模式下生成的项目骨架结构。
使用 MockExecutor 替代真实 SandboxExecutor，无需 Docker 环境即可运行。

运行方式（从项目根目录）：
    python -m pytest agent_builder/test/test_create_project.py -v
    python agent_builder/test/test_create_project.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_BUILDER = PROJECT_ROOT / "agent_builder"

sys.path.insert(0, str(AGENT_BUILDER))

# ── MockExecutor ──────────────────────────────────────────────────────────────

class MockExecResult:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class MockExecutor:
    def __init__(self):
        self.files: dict[str, str] = {}
        self.dirs: list[str] = []

    def run(self, command: list, workdir: str = "/workspace", timeout: int = 30) -> MockExecResult:  # noqa: ARG002
        if command[:2] == ["test", "-f"]:
            path = command[2]
            return MockExecResult(returncode=0 if path in self.files else 1)
        if command[:2] == ["mkdir", "-p"]:
            self.dirs.append(command[2])
            return MockExecResult()
        return MockExecResult()

    def write_file(self, container_path: str, content: str) -> MockExecResult:
        self.files[container_path] = content
        return MockExecResult()


# ── 加载模块 ──────────────────────────────────────────────────────────────────

def _load_module(script_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module(AGENT_BUILDER / "project_create" / "creat_project.py", "creat_project")
create_project = _mod.create_project

EXPECTED_DIRS = [
    "Agent", "Model", "Workflow", "Context",
    "Prompt", "Skill", "Config", "Finish_MarkDown", "Test",
]

# ── 测试用例 ──────────────────────────────────────────────────────────────────

def test_all_dirs_created() -> None:
    """所有期望目录应通过 mkdir -p 创建。"""
    executor = MockExecutor()
    create_project("test_proj", executor=executor)
    for d in EXPECTED_DIRS:
        expected = f"/workspace/test_proj/{d}"
        assert expected in executor.dirs, f"目录未创建：{expected}"


def test_env_file_created() -> None:
    """.env 文件应被写入容器。"""
    executor = MockExecutor()
    create_project("test_proj", executor=executor)
    assert "/workspace/test_proj/.env" in executor.files, ".env 文件未生成"


def test_no_tool_config_toml() -> None:
    """工具相关配置和目录不应被创建。"""
    executor = MockExecutor()
    create_project("test_proj", executor=executor)
    assert "/workspace/test_proj/Tools" not in executor.dirs
    assert "/workspace/test_proj/Config/tool_config.toml" not in executor.files


def test_no_overwrite_existing_file() -> None:
    """已存在的文件不应被覆盖。"""
    executor = MockExecutor()
    executor.files["/workspace/test_proj/.env"] = "# sentinel"
    create_project("test_proj", executor=executor)
    assert executor.files["/workspace/test_proj/.env"] == "# sentinel"


def test_spaces_in_name_normalized() -> None:
    """项目名中的空格应被替换为下划线。"""
    executor = MockExecutor()
    create_project("my project", executor=executor)
    assert any("/workspace/my_project/" in d for d in executor.dirs)


def test_returns_correct_base_path() -> None:
    """返回值应为容器内的正确路径。"""
    executor = MockExecutor()
    result = create_project("my_agent", executor=executor)
    assert result == "/workspace/my_agent"


# ── 简易运行器 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_all_dirs_created,
        test_env_file_created,
        test_no_tool_config_toml,
        test_no_overwrite_existing_file,
        test_spaces_in_name_normalized,
        test_returns_correct_base_path,
    ]

    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
