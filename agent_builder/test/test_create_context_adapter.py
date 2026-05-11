"""
test_create_context_adapter.py

测试 agent_builder/context_create/create_context_adapter.py 的核心逻辑。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parent.parent / "context_create" / "create_context_adapter.py"
_spec = importlib.util.spec_from_file_location("create_context_adapter", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

create_context_adapter = _mod.create_context_adapter


def _target_context(root: Path) -> Path:
    return root / "Context" / "standard_markdown.md"


def test_create_context_adapter_generates_files(tmp_path: Path) -> None:
    original_root = _mod.MAIN_AGENT_ROOT
    _mod.MAIN_AGENT_ROOT = tmp_path / "main_agent"
    try:
        target = _target_context(_mod.MAIN_AGENT_ROOT)
        assert not target.exists()
        create_context_adapter()
        assert target.exists(), "standard_markdown.md 未生成"
    finally:
        _mod.MAIN_AGENT_ROOT = original_root


def test_adapter_file_content(tmp_path: Path) -> None:
    original_root = _mod.MAIN_AGENT_ROOT
    _mod.MAIN_AGENT_ROOT = tmp_path / "main_agent"
    try:
        create_context_adapter()
        content = _target_context(_mod.MAIN_AGENT_ROOT).read_text(encoding="utf-8")
        # 核心结构与锚点应该存在
        assert "<!-- AVAILABLE_TOOLS_START -->" in content
        assert "<!-- STANDARD_FIELDS_START -->" in content
        assert "<!-- AGENT_CONTEXT_START -->" in content
        assert "<!-- EXTERNAL_INFO_START -->" in content
    finally:
        _mod.MAIN_AGENT_ROOT = original_root


def test_no_overwrite_existing(tmp_path: Path) -> None:
    original_root = _mod.MAIN_AGENT_ROOT
    _mod.MAIN_AGENT_ROOT = tmp_path / "main_agent"
    try:
        ctx_file = _target_context(_mod.MAIN_AGENT_ROOT)
        ctx_file.parent.mkdir(parents=True, exist_ok=True)
        ctx_file.write_text("# sentinel", encoding="utf-8")
        create_context_adapter()
        assert ctx_file.read_text(encoding="utf-8") == "# sentinel"
    finally:
        _mod.MAIN_AGENT_ROOT = original_root


if __name__ == "__main__":
    import tempfile

    tests = [
        test_create_context_adapter_generates_files,
        test_adapter_file_content,
        test_no_overwrite_existing,
    ]
    passed = 0
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            with tempfile.TemporaryDirectory() as tmp:
                test(Path(tmp))
            print(f"PASS  {name}")
            passed += 1
        except TypeError:
            try:
                test()
                print(f"PASS  {name}")
                passed += 1
            except Exception as e:
                print(f"FAIL  {name}: {e}")
                failed += 1
        except Exception as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
