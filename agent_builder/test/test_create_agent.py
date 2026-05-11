"""
test_create_agent.py

测试 agent_builder/agent_create/create_agent.py 的核心逻辑。

运行方式（从项目根目录）：
    python -m pytest agent_builder/test/test_create_agent.py -v
    # 或直接运行：
    python agent_builder/test/test_create_agent.py
"""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

# ── 把 create_agent 模块加载进来 ──────────────────────────────────────────────
_SCRIPT = Path(__file__).resolve().parent.parent / "agent_create" / "create_agent.py"
_spec = importlib.util.spec_from_file_location("create_agent", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

create_agent = _mod.create_agent
to_class_prefix = _mod.to_class_prefix


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _cleanup(tmp_root: Path, name: str) -> None:
    """删除测试生成的临时文件。"""
    for p in [
        tmp_root / "Agent" / f"{name}_agent.py",
        tmp_root / "Prompt" / f"{name}_agent.md",
    ]:
        if p.exists():
            p.unlink()


# ── 测试用例 ──────────────────────────────────────────────────────────────────

def test_to_class_prefix_simple():
    assert to_class_prefix("researcher") == "Researcher"


def test_to_class_prefix_underscore():
    assert to_class_prefix("data_analyst") == "DataAnalyst"


def test_to_class_prefix_multi():
    assert to_class_prefix("my_custom_agent") == "MyCustomAgent"


def test_create_agent_generates_files(tmp_path: Path):
    """create_agent 应在 tmp_path 下生成 Agent/ 和 Prompt/ 两个文件。"""
    # 临时覆盖 PROJECT_ROOT，让脚本写到 tmp_path
    original_root = _mod.PROJECT_ROOT
    _mod.PROJECT_ROOT = tmp_path
    try:
        create_agent("tester")
        agent_file = tmp_path / "Agent" / "tester_agent.py"
        prompt_file = tmp_path / "Prompt" / "tester_agent.md"
        assert agent_file.exists(), "Agent 文件未生成"
        assert prompt_file.exists(), "Prompt 文件未生成"
    finally:
        _mod.PROJECT_ROOT = original_root


def test_agent_file_content(tmp_path: Path):
    """生成的 Agent 文件应包含正确的类名和 agent_type。"""
    original_root = _mod.PROJECT_ROOT
    _mod.PROJECT_ROOT = tmp_path
    try:
        create_agent("reviewer")
        content = (tmp_path / "Agent" / "reviewer_agent.py").read_text(encoding="utf-8")
        assert "class ReviewerAgent(BaseAgent)" in content
        assert 'agent_type="reviewer"' in content
        assert 'prompt_file: str = "reviewer_agent.md"' in content
    finally:
        _mod.PROJECT_ROOT = original_root


def test_prompt_file_content(tmp_path: Path):
    """生成的 Prompt 文件应包含 agent 名称。"""
    original_root = _mod.PROJECT_ROOT
    _mod.PROJECT_ROOT = tmp_path
    try:
        create_agent("reviewer")
        content = (tmp_path / "Prompt" / "reviewer_agent.md").read_text(encoding="utf-8")
        assert "Reviewer" in content
        assert "reviewer" in content
    finally:
        _mod.PROJECT_ROOT = original_root


def test_no_overwrite_existing(tmp_path: Path):
    """已存在的文件不应被覆盖。"""
    original_root = _mod.PROJECT_ROOT
    _mod.PROJECT_ROOT = tmp_path
    try:
        create_agent("guard")
        agent_file = tmp_path / "Agent" / "guard_agent.py"
        # 写入标记内容
        agent_file.write_text("# sentinel", encoding="utf-8")
        # 再次调用，不应覆盖
        create_agent("guard")
        assert agent_file.read_text(encoding="utf-8") == "# sentinel"
    finally:
        _mod.PROJECT_ROOT = original_root


def test_hyphen_normalized(tmp_path: Path):
    """连字符应被转换为下划线。"""
    original_root = _mod.PROJECT_ROOT
    _mod.PROJECT_ROOT = tmp_path
    try:
        create_agent("data-analyst")
        assert (tmp_path / "Agent" / "data_analyst_agent.py").exists()
        assert (tmp_path / "Prompt" / "data_analyst_agent.md").exists()
    finally:
        _mod.PROJECT_ROOT = original_root


# ── 简易运行器（无 pytest 时也可直接执行）────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    tests = [
        test_to_class_prefix_simple,
        test_to_class_prefix_underscore,
        test_to_class_prefix_multi,
    ]
    path_tests = [
        test_create_agent_generates_files,
        test_agent_file_content,
        test_prompt_file_content,
        test_no_overwrite_existing,
        test_hyphen_normalized,
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

    for t in path_tests:
        with tempfile.TemporaryDirectory() as td:
            try:
                t(Path(td))
                print(f"  PASS  {t.__name__}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {t.__name__}: {e}")
                failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
