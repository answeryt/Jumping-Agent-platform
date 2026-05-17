"""
test_sandbox_tools.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
沙盒工具单元测试：验证 CodeSandbox 与 SandboxTool 的核心功能。

运行方式：
  cd back_agent
  python -m pytest test/test_sandbox_tools.py -v
  # 或直接运行：
  python test/test_sandbox_tools.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# 把 back_agent 加入路径
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from tools.sandbox_tools import CodeSandbox, SandboxTool, build_sandbox_tool
from tools.shell_tool_adapter import build_sandbox_bridge
from tools.sandbox_diagnostic_tools import build_sandbox_diagnostics_tool

# ── 目标项目路径（用 back_agent 自身作为测试项目）─────────────────────
_PROJECT = Path(__file__).resolve().parent.parent
_PROJECT_STR = _PROJECT.as_posix()


# ──────────────────────────────────────────────────────────────────────
# 辅助
# ──────────────────────────────────────────────────────────────────────

def _load() -> CodeSandbox:
    sb = CodeSandbox()
    result = sb.load(_PROJECT_STR)
    assert "[ERROR]" not in result, f"load 失败: {result}"
    return sb


# ──────────────────────────────────────────────────────────────────────
# 测试：load
# ──────────────────────────────────────────────────────────────────────

def test_load_returns_summary():
    sb = _load()
    assert sb._loaded
    assert sb.root is not None
    assert len(sb.content_cache) > 0
    assert len(sb.symbol_index) > 0
    print("  [PASS] test_load_returns_summary")


def test_load_indexes_known_class():
    sb = _load()
    assert "SandboxTool" in sb.symbol_index, "SandboxTool 应在符号索引中"
    assert "ToolBridge" in sb.symbol_index, "ToolBridge 应在符号索引中"
    print("  [PASS] test_load_indexes_known_class")


def test_load_not_loaded_error():
    sb = CodeSandbox()
    result = sb.find("anything")
    assert "[ERROR]" in result
    print("  [PASS] test_load_not_loaded_error")


def test_load_invalid_path():
    sb = CodeSandbox()
    result = sb.load("C:/nonexistent/path/xyz")
    assert "[ERROR]" in result
    print("  [PASS] test_load_invalid_path")


# ──────────────────────────────────────────────────────────────────────
# 测试：tree
# ──────────────────────────────────────────────────────────────────────

def test_tree_contains_directories():
    sb = _load()
    tree = sb.tree(depth=2)
    assert "tools/" in tree or "agent/" in tree, "tree 应包含已知子目录"
    print("  [PASS] test_tree_contains_directories")


def test_tree_annotates_py_files():
    sb = _load()
    tree = sb.tree(depth=3)
    # sandbox_tools.py 应附带 SandboxTool / CodeSandbox 类名
    assert "SandboxTool" in tree or "sandbox_tools" in tree
    print("  [PASS] test_tree_annotates_py_files")


# ──────────────────────────────────────────────────────────────────────
# 测试：find
# ──────────────────────────────────────────────────────────────────────

def test_find_class_by_name():
    sb = _load()
    result = sb.find("SandboxTool")
    assert "[class]" in result
    assert "sandbox_tools" in result
    print("  [PASS] test_find_class_by_name")


def test_find_method_by_name():
    sb = _load()
    result = sb.find("load_project")
    assert "load_project" in result
    print("  [PASS] test_find_method_by_name")


def test_find_file_by_partial_name():
    sb = _load()
    result = sb.find("sandbox_tools")
    assert "[file]" in result or "sandbox_tools" in result
    print("  [PASS] test_find_file_by_partial_name")


def test_find_fulltext_fallback():
    sb = _load()
    result = sb.find("DEFAULT_TIMEOUT")
    assert "DEFAULT_TIMEOUT" in result
    print("  [PASS] test_find_fulltext_fallback")


def test_find_notfound():
    sb = CodeSandbox()
    # 只加载 tools/ 子目录，该目录下不包含本测试文件，因此随机字符串不会被全文找到
    sb.load((_PROJECT / "tools").as_posix())
    result = sb.find("ZZZZZNOTEXIST99887766XQWERTY")
    assert "未找到" in result
    print("  [PASS] test_find_notfound")


# ──────────────────────────────────────────────────────────────────────
# 测试：get
# ──────────────────────────────────────────────────────────────────────

def test_get_class_by_name():
    sb = _load()
    result = sb.get("SandboxTool")
    assert "class SandboxTool" in result
    assert "[class]" in result
    print("  [PASS] test_get_class_by_name")


def test_get_file_by_partial_path():
    sb = _load()
    # 使用精确到目录层级的路径，避免模糊匹配到测试文件
    result = sb.get("tools/sandbox_tools.py")
    assert "SandboxTool" in result
    print("  [PASS] test_get_file_by_partial_path")


def test_get_around_line():
    sb = _load()
    # sandbox_tools.py 的第 1 行附近
    result = sb.get("tools/sandbox_tools.py:1")
    assert "tools/sandbox_tools.py" in result
    assert "|" in result   # 行号格式 "  1 | ..."
    print("  [PASS] test_get_around_line")


def test_get_notfound():
    sb = _load()
    result = sb.get("__nonexistent_file_xyz.py")
    assert "未找到" in result
    print("  [PASS] test_get_notfound")


# ──────────────────────────────────────────────────────────────────────
# 测试：config
# ──────────────────────────────────────────────────────────────────────

def test_config_loads_toml():
    sb = _load()
    cfg = sb.config()
    # back_agent 有 model_config.toml 或其他 toml
    if cfg == "(未找到配置文件)":
        print("  [SKIP] test_config_loads_toml (无配置文件)")
        return
    assert "===" in cfg
    print("  [PASS] test_config_loads_toml")


def test_config_masks_sensitive():
    sb = CodeSandbox()
    # 构造含敏感字段的 dotenv 内容
    dotenv_content = "MY_API_KEY=sk-abcdefghijk\nNORMAL=hello"
    parsed = sb._parse_dotenv(dotenv_content)
    assert parsed["MY_API_KEY"].endswith("****"), "敏感字段应脱敏"
    assert parsed["NORMAL"] == "hello", "普通字段不应脱敏"
    print("  [PASS] test_config_masks_sensitive")


# ──────────────────────────────────────────────────────────────────────
# 测试：SandboxTool 工具接口（返回值格式）
# ──────────────────────────────────────────────────────────────────────

def test_sandbox_tool_load_project():
    tool = SandboxTool()
    result = tool.load_project(_PROJECT_STR)
    assert result["ok"] is True
    assert result["returncode"] == 0
    assert "项目已加载" in result["stdout"]
    print("  [PASS] test_sandbox_tool_load_project")


def test_sandbox_tool_find():
    tool = SandboxTool()
    tool.load_project(_PROJECT_STR)
    result = tool.find("SandboxTool")
    assert result["ok"] is True
    assert "SandboxTool" in result["stdout"]
    print("  [PASS] test_sandbox_tool_find")


def test_sandbox_tool_get():
    tool = SandboxTool()
    tool.load_project(_PROJECT_STR)
    result = tool.get("SandboxTool")
    assert result["ok"] is True
    assert "class SandboxTool" in result["stdout"]
    print("  [PASS] test_sandbox_tool_get")


def test_sandbox_tool_tree():
    tool = SandboxTool()
    tool.load_project(_PROJECT_STR)
    result = tool.tree(depth=2)
    assert result["ok"] is True
    assert result["returncode"] == 0
    print("  [PASS] test_sandbox_tool_tree")


# ──────────────────────────────────────────────────────────────────────
# 测试：ToolBridge 集成
# ──────────────────────────────────────────────────────────────────────

def test_build_sandbox_bridge_registers_all_tools():
    bridge, tool = build_sandbox_bridge()
    expected = {
        "load_project",
        "tree",
        "find",
        "get",
        "config",
        "write_file",
        "patch_symbol",
        "replace_lines",
        "run_python",
        "check_syntax",
        "check_imports",
        "diagnose_python",
    }
    registered = set(bridge._tools.keys())
    assert expected == registered, f"注册的工具不匹配: {registered}"
    print("  [PASS] test_build_sandbox_bridge_registers_all_tools")


def test_sandbox_bridge_execute_load():
    from tools.tool_bridge import ParsedToolCall
    bridge, _ = build_sandbox_bridge()
    call = ParsedToolCall(
        tool_name="load_project",
        args=[_PROJECT_STR],
        kwargs={},
        raw=f'tool_call("load_project", "{_PROJECT_STR}")',
    )
    result = bridge.execute_call(call)
    assert result["ok"] is True
    print("  [PASS] test_sandbox_bridge_execute_load")


def test_diagnostics_tool_check_syntax_detects_error():
    tool = SandboxTool()
    tool.load_project(_PROJECT_STR)
    diagnostics = build_sandbox_diagnostics_tool(tool)
    bad_path = _PROJECT / "tmp_syntax_error_case.py"
    bad_path.write_text("def broken():\nprint('x')\n", encoding="utf-8")
    try:
        tool.load_project(_PROJECT_STR)
        result = diagnostics.check_syntax("tmp_syntax_error_case.py")
        assert result["ok"] is False
        assert "IndentationError" in result["stdout"] or "SyntaxError" in result["stdout"]
        print("  [PASS] test_diagnostics_tool_check_syntax_detects_error")
    finally:
        if bad_path.exists():
            bad_path.unlink()


def test_diagnostics_tool_check_imports_detects_missing_module():
    tool = SandboxTool()
    tool.load_project(_PROJECT_STR)
    diagnostics = build_sandbox_diagnostics_tool(tool)
    bad_path = _PROJECT / "tmp_import_error_case.py"
    bad_path.write_text("import definitely_missing_module_123\n", encoding="utf-8")
    try:
        tool.load_project(_PROJECT_STR)
        result = diagnostics.check_imports("tmp_import_error_case.py")
        assert result["ok"] is False
        assert "definitely_missing_module_123" in result["stdout"]
        print("  [PASS] test_diagnostics_tool_check_imports_detects_missing_module")
    finally:
        if bad_path.exists():
            bad_path.unlink()


def test_diagnostics_tool_check_imports_detects_missing_annotation_import():
    tool = SandboxTool()
    tool.load_project(_PROJECT_STR)
    diagnostics = build_sandbox_diagnostics_tool(tool)
    bad_path = _PROJECT / "tmp_annotation_import_error_case.py"
    bad_path.write_text(
        "from __future__ import annotations\n\n"
        "from typing import Any, Dict, List\n\n"
        "def broken(metadata: Optional[Dict[str, Any]] = None) -> List[str]:\n"
        "    return []\n",
        encoding="utf-8",
    )
    try:
        tool.load_project(_PROJECT_STR)
        result = diagnostics.check_imports("tmp_annotation_import_error_case.py")
        assert result["ok"] is False
        assert "undefined_annotation_name" in result["stdout"]
        assert "Optional" in result["stdout"]
        print("  [PASS] test_diagnostics_tool_check_imports_detects_missing_annotation_import")
    finally:
        if bad_path.exists():
            bad_path.unlink()


def test_diagnostics_tool_run_python_executes_file():
    tool = SandboxTool()
    tool.load_project(_PROJECT_STR)
    diagnostics = build_sandbox_diagnostics_tool(tool)
    script_path = _PROJECT / "tmp_run_python_case.py"
    script_path.write_text("print('hello-diagnostics')\n", encoding="utf-8")
    try:
        tool.load_project(_PROJECT_STR)
        result = diagnostics.run_python("tmp_run_python_case.py")
        assert result["ok"] is True
        assert "hello-diagnostics" in result["stdout"]
        print("  [PASS] test_diagnostics_tool_run_python_executes_file")
    finally:
        if script_path.exists():
            script_path.unlink()


# ──────────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────────

def _run_all():
    tests = [
        test_load_returns_summary,
        test_load_indexes_known_class,
        test_load_not_loaded_error,
        test_load_invalid_path,
        test_tree_contains_directories,
        test_tree_annotates_py_files,
        test_find_class_by_name,
        test_find_method_by_name,
        test_find_file_by_partial_name,
        test_find_fulltext_fallback,
        test_find_notfound,
        test_get_class_by_name,
        test_get_file_by_partial_path,
        test_get_around_line,
        test_get_notfound,
        test_config_loads_toml,
        test_config_masks_sensitive,
        test_sandbox_tool_load_project,
        test_sandbox_tool_find,
        test_sandbox_tool_get,
        test_sandbox_tool_tree,
        test_build_sandbox_bridge_registers_all_tools,
        test_sandbox_bridge_execute_load,
        test_diagnostics_tool_check_syntax_detects_error,
        test_diagnostics_tool_check_imports_detects_missing_module,
        test_diagnostics_tool_check_imports_detects_missing_annotation_import,
        test_diagnostics_tool_run_python_executes_file,
    ]

    sep = "─" * 60
    print(f"\n{sep}")
    print("  沙盒工具单元测试")
    print(sep)

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {t.__name__}: {exc}")
            failed += 1

    print(sep)
    print(f"  结果: {passed} 通过 / {failed} 失败 / {len(tests)} 总计")
    print(sep)
    return failed


if __name__ == "__main__":
    failures = _run_all()
    sys.exit(failures)
