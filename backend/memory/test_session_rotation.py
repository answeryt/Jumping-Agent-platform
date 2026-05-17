# -*- coding: utf-8 -*-
"""Verify the two-tier session manager rotates md files correctly."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.memory.memory_template_writer import (  # noqa: E402
    AGENT_INFO_END,
    AGENT_INFO_START,
)
from backend.memory.working_memory import (  # noqa: E402
    AgentWorkingMemory,
    MAX_TURNS_PER_SMALL_SESSION,
    SessionManager,
)


def _make_manager(tmp_path: Path) -> SessionManager:
    return SessionManager(sessions_root=tmp_path / "sessions")


def test_small_session_reuses_md_within_quota_and_rotates_after(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    big_id = manager.start_big_session("big_test")

    first = manager.pick_or_create_small_session(big_id)
    assert first.md_path.exists()

    for _ in range(MAX_TURNS_PER_SMALL_SESSION):
        same = manager.pick_or_create_small_session(big_id)
        assert same.md_path == first.md_path
        assert same.small_session_id == first.small_session_id
        manager.record_user_turn(same)

    rotated = manager.pick_or_create_small_session(big_id)
    assert rotated.small_session_id != first.small_session_id
    assert rotated.md_path != first.md_path
    assert rotated.md_path.exists()


def test_different_big_sessions_are_isolated(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    big_a = manager.start_big_session("big_a")
    big_b = manager.start_big_session("big_b")

    small_a = manager.pick_or_create_small_session(big_a)
    small_b = manager.pick_or_create_small_session(big_b)

    assert small_a.md_path.parent != small_b.md_path.parent
    assert manager.list_small_sessions(big_a)[0]["md_path"] == str(small_a.md_path)
    assert manager.list_small_sessions(big_b)[0]["md_path"] == str(small_b.md_path)


def test_for_md_session_appends_agent_outputs_to_md(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    big_id = manager.start_big_session("big_md")

    db_path = tmp_path / "working_memory.sqlite3"
    memory = AgentWorkingMemory.for_md_session(
        user_id="tester",
        big_session_id=big_id,
        sessions_root=manager.sessions_root,
        db_path=db_path,
        session_manager=manager,
    )

    memory.append("user", "请告诉我最近的新闻", agent_key="shared")
    memory.append("assistant", "Manager 分析了任务。", agent_key="manager", turn_index=1)
    memory.append("assistant", "Researcher 收集了素材。", agent_key="researcher", turn_index=2)

    content = memory.md_path.read_text(encoding="utf-8")
    assert AGENT_INFO_START in content and AGENT_INFO_END in content
    assert "对应名称：manager" in content
    assert "对应名称：researcher" in content
    assert "Manager 分析了任务。" in content
    assert "Researcher 收集了素材。" in content


def test_for_md_session_requires_user_id(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    big_id = manager.start_big_session("big_no_user")

    with pytest.raises(TypeError):
        AgentWorkingMemory.for_md_session(  # type: ignore[call-arg]
            big_session_id=big_id,
            sessions_root=manager.sessions_root,
            session_manager=manager,
        )
