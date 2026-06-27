from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("WEIXIN_BRIDGE_AUTO_START", "0")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

from backend.orchestrator import _write_text  # noqa: E402


def _temp_files_for(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f".{path.name}.*.tmp"))


def test_write_text_replaces_file_after_temp_write(tmp_path: Path) -> None:
    target = tmp_path / "Agent" / "demo_agent.py"
    generated: list[str] = []

    _write_text(target, "new content", generated, tmp_path)

    assert target.read_text(encoding="utf-8") == "new content"
    assert generated == ["Agent/demo_agent.py"]
    assert _temp_files_for(target) == []


def test_write_text_keeps_existing_file_when_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "Agent" / "demo_agent.py"
    target.parent.mkdir(parents=True)
    target.write_text("old content", encoding="utf-8")
    generated: list[str] = []

    original_replace = Path.replace

    def fail_replace(self: Path, target_path: Any) -> Path:
        if target_path == target:
            raise RuntimeError("replace failed")
        return original_replace(self, target_path)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(RuntimeError, match="replace failed"):
        _write_text(target, "new content", generated, tmp_path)

    assert target.read_text(encoding="utf-8") == "old content"
    assert generated == []
    assert _temp_files_for(target) == []
