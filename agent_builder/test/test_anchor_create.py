"""
test_anchor_create.py

测试 agent_builder/anchor_create/anchor_create.py 的核心逻辑。

运行方式（从项目根目录）：
    python -m pytest agent_builder/test/test_anchor_create.py -v
    python agent_builder/test/test_anchor_create.py
"""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

# ── 加载 anchor_create 模块 ───────────────────────────────────────────────────
_SCRIPT = Path(__file__).resolve().parent.parent / "anchor_create" / "anchor_create.py"
_spec = importlib.util.spec_from_file_location("anchor_create", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

normalize_agent_name = _mod.normalize_agent_name
extract_anchor_template = _mod.extract_anchor_template
create_anchor_template = _mod.create_anchor_template
TEMPLATE_PATH = _mod.TEMPLATE_PATH

# ── 最小测试模板（内联，不依赖真实文件）──────────────────────────────────────
_MINI_TEMPLATE = """\
<!-- STANDARD_FIELDS_START -->
some content
<!-- STANDARD_FIELDS_END -->

<!-- AGENT_CONTEXT_START -->
goal:

<!-- INTERACTION_AGENT_GOAL_START -->

<!-- INTERACTION_AGENT_GOAL_END -->

<!-- PLANNING_AGENTS_GOAL_START -->

<!-- PLANNING_AGENTS_GOAL_END -->

<!-- ACTION_AGENTS_GOAL_START -->

<!-- ACTION_AGENTS_GOAL_END -->

known_info:
<!-- INTERACTION_AGENT_KNOWN_INFO_START -->

<!-- INTERACTION_AGENT_KNOWN_INFO_END -->

<!-- PLANNING_AGENTS_KNOWN_INFO_START -->

<!-- PLANNING_AGENTS_KNOWN_INFO_END -->

<!-- AGENT_CONTEXT_END -->
"""


# ── 测试用例 ──────────────────────────────────────────────────────────────────

def test_normalize_agent_name_basic():
    assert normalize_agent_name("interaction") == "INTERACTION"


def test_normalize_agent_name_hyphen():
    assert normalize_agent_name("data-analyst") == "DATA_ANALYST"


def test_normalize_agent_name_uppercase_input():
    assert normalize_agent_name("PLANNING") == "PLANNING"


def test_normalize_agent_name_whitespace():
    assert normalize_agent_name("  action  ") == "ACTION"


def test_extract_keeps_matching_anchors():
    """interaction 的锚点应保留。"""
    result = extract_anchor_template("interaction", _MINI_TEMPLATE)
    assert "<!-- INTERACTION_AGENT_GOAL_START -->" in result
    assert "<!-- INTERACTION_AGENT_GOAL_END -->" in result
    assert "<!-- INTERACTION_AGENT_KNOWN_INFO_START -->" in result


def test_extract_removes_other_anchors():
    """其他 agent 的锚点应被删除。"""
    result = extract_anchor_template("interaction", _MINI_TEMPLATE)
    assert "<!-- PLANNING_AGENTS_GOAL_START -->" not in result
    assert "<!-- PLANNING_AGENTS_GOAL_END -->" not in result
    assert "<!-- ACTION_AGENTS_GOAL_START -->" not in result
    assert "<!-- PLANNING_AGENTS_KNOWN_INFO_START -->" not in result


def test_extract_keeps_structural_anchors():
    """结构锚点（非业务锚点）应保持不变。"""
    result = extract_anchor_template("interaction", _MINI_TEMPLATE)
    assert "<!-- STANDARD_FIELDS_START -->" in result
    assert "<!-- STANDARD_FIELDS_END -->" in result
    assert "<!-- AGENT_CONTEXT_START -->" in result
    assert "<!-- AGENT_CONTEXT_END -->" in result


def test_extract_keeps_plain_content():
    """普通文本内容不应被删除。"""
    result = extract_anchor_template("interaction", _MINI_TEMPLATE)
    assert "some content" in result
    assert "goal:" in result
    assert "known_info:" in result


def test_extract_planning_agent():
    """planning agent 应保留 PLANNING_AGENTS 锚点，删除其他。"""
    result = extract_anchor_template("planning", _MINI_TEMPLATE)
    assert "<!-- PLANNING_AGENTS_GOAL_START -->" in result
    assert "<!-- PLANNING_AGENTS_GOAL_END -->" in result
    assert "<!-- INTERACTION_AGENT_GOAL_START -->" not in result
    assert "<!-- ACTION_AGENTS_GOAL_START -->" not in result


def test_extract_action_agent():
    """action agent 应保留 ACTION_AGENTS 锚点，删除其他。"""
    result = extract_anchor_template("action", _MINI_TEMPLATE)
    assert "<!-- ACTION_AGENTS_GOAL_START -->" in result
    assert "<!-- ACTION_AGENTS_GOAL_END -->" in result
    assert "<!-- INTERACTION_AGENT_GOAL_START -->" not in result
    assert "<!-- PLANNING_AGENTS_GOAL_START -->" not in result


def test_create_anchor_template_write_file(tmp_path: Path):
    """create_anchor_template 应正确写入文件。"""
    out = tmp_path / "interaction_context.md"
    # 用真实模板文件测试
    if not TEMPLATE_PATH.exists():
        print("  SKIP  test_create_anchor_template_write_file: 模板文件不存在")
        return
    create_anchor_template("interaction", output_path=out)
    assert out.exists(), "输出文件未生成"
    content = out.read_text(encoding="utf-8")
    assert "<!-- INTERACTION_AGENT_GOAL_START -->" in content
    assert "<!-- PLANNING_AGENTS_GOAL_START -->" not in content


def test_create_anchor_template_returns_string():
    """create_anchor_template 应返回字符串内容。"""
    if not TEMPLATE_PATH.exists():
        print("  SKIP  test_create_anchor_template_returns_string: 模板文件不存在")
        return
    result = create_anchor_template("interaction")
    assert isinstance(result, str)
    assert len(result) > 0


def test_real_template_all_suffixes_preserved():
    """真实模板中，interaction 的所有字段锚点后缀应完整保留。"""
    if not TEMPLATE_PATH.exists():
        print("  SKIP  test_real_template_all_suffixes_preserved: 模板文件不存在")
        return
    result = create_anchor_template("interaction")
    expected_anchors = [
        "<!-- INTERACTION_AGENT_GOAL_START -->",
        "<!-- INTERACTION_AGENT_GOAL_END -->",
        "<!-- INTERACTION_AGENT_USER_REQUEST_START -->",
        "<!-- INTERACTION_AGENT_USER_REQUEST_END -->",
        "<!-- INTERACTION_AGENT_KNOWN_INFO_START -->",
        "<!-- INTERACTION_AGENT_KNOWN_INFO_END -->",
        "<!-- INTERACTION_AGENT_PHASE_START -->",
        "<!-- INTERACTION_AGENT_PHASE_END -->",
        "<!-- INTERACTION_AGENT_CONSTRAINTS_START -->",
        "<!-- INTERACTION_AGENT_CONSTRAINTS_END -->",
        "<!-- INTERACTION_AGENT_RESULT_START -->",
        "<!-- INTERACTION_AGENT_RESULT_END -->",
        "<!-- INTERACTION_AGENT_STEPS_START -->",
        "<!-- INTERACTION_AGENT_STEPS_END -->",
        "<!-- INTERACTION_AGENT_SKILLS_USED_START -->",
        "<!-- INTERACTION_AGENT_SKILLS_USED_END -->",
        "<!-- INTERACTION_AGENT_NEXT_AGENT_START -->",
        "<!-- INTERACTION_AGENT_NEXT_AGENT_END -->",
        "<!-- INTERACTION_AGENT_NEXT_TASK_START -->",
        "<!-- INTERACTION_AGENT_NEXT_TASK_END -->",
        "<!-- INTERACTION_AGENT_NOTES_START -->",
        "<!-- INTERACTION_AGENT_NOTES_END -->",
    ]
    for anchor in expected_anchors:
        assert anchor in result, f"缺少锚点：{anchor}"


# ── 简易运行器 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    simple_tests = [
        test_normalize_agent_name_basic,
        test_normalize_agent_name_hyphen,
        test_normalize_agent_name_uppercase_input,
        test_normalize_agent_name_whitespace,
        test_extract_keeps_matching_anchors,
        test_extract_removes_other_anchors,
        test_extract_keeps_structural_anchors,
        test_extract_keeps_plain_content,
        test_extract_planning_agent,
        test_extract_action_agent,
        test_create_anchor_template_returns_string,
        test_real_template_all_suffixes_preserved,
    ]

    path_tests = [
        test_create_anchor_template_write_file,
    ]

    passed = failed = 0

    for t in simple_tests:
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
