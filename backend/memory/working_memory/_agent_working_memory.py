# -*- coding: utf-8 -*-
"""Unified short-term memory for generated agents.

The generated agent flows are synchronous, so this module provides a small
SQLite-backed facade that can be used directly from those flow templates.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ._context_compaction import (
    AutoCompactTrackingState,
    CompactionResult,
    SessionMemoryCompactConfig,
    auto_compact_if_needed,
    calculate_token_warning_state,
    estimate_message_tokens,
    get_auto_compact_threshold,
)
from ._session_manager import SessionManager, SmallSessionBinding

ChatMessage = dict[str, str]


class AgentWorkingMemory:
    """Persistent short-term memory shared by all generated agents.

    Two ways to construct:

    - Pass explicit ``user_id`` / ``session_id`` strings (low level, no md
      side-effects). The caller is responsible for any markdown bookkeeping.
    - Use :meth:`for_md_session` to bind a big/small session pair. Each
      :meth:`append` then mirrors Agent outputs and tool counts into the bound
      markdown file via ``memory_template_writer.update_memory_template``.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        user_id: str,
        session_id: str,
        md_path: str | Path | None = None,
        big_session_id: str | None = None,
        small_session_id: str | None = None,
    ) -> None:
        default_db = Path(__file__).resolve().parent / "working_memory.sqlite3"
        self.db_path = Path(
            db_path or os.getenv("AGENT_WORKING_MEMORY_DB") or default_db,
        )
        self.user_id = user_id
        self.session_id = session_id
        self.md_path: Optional[Path] = Path(md_path) if md_path else None
        self.big_session_id = big_session_id
        self.small_session_id = small_session_id
        self._lock = threading.RLock()
        self._ensure_schema()

    @classmethod
    def for_md_session(
        cls,
        *,
        user_id: str,
        big_session_id: str,
        small_session_id: str | None = None,
        sessions_root: str | Path | None = None,
        template_path: str | Path | None = None,
        db_path: str | Path | None = None,
        session_manager: SessionManager | None = None,
    ) -> "AgentWorkingMemory":
        """Bind a memory handle to a small-session markdown file.

        If ``small_session_id`` is omitted the manager picks the active small
        session (or rolls a new one when the previous one filled its 10-turn
        quota). The resulting memory's ``session_id`` is the composite
        ``big/small`` so SQLite rows stay isolated per small session.
        """
        manager = session_manager or SessionManager(sessions_root=sessions_root)
        if small_session_id:
            md_path = manager.big_session_dir(big_session_id) / f"{small_session_id}.md"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            if not md_path.exists():
                from ..memory_template_writer import create_session_memory_template

                create_session_memory_template(template_path=template_path, dest_path=md_path)
            binding = SmallSessionBinding(
                big_session_id=big_session_id,
                small_session_id=small_session_id,
                md_path=md_path,
                turns_used=0,
            )
        else:
            binding = manager.pick_or_create_small_session(
                big_session_id, template_path=template_path
            )
        return cls(
            db_path=db_path,
            user_id=user_id,
            session_id=binding.composite_session_id,
            md_path=binding.md_path,
            big_session_id=binding.big_session_id,
            small_session_id=binding.small_session_id,
        )

    def for_session(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        md_path: str | Path | None = None,
        big_session_id: str | None = None,
        small_session_id: str | None = None,
    ) -> "AgentWorkingMemory":
        """Create a memory handle pointing at the same store."""
        return AgentWorkingMemory(
            self.db_path,
            user_id=user_id or self.user_id,
            session_id=session_id or self.session_id,
            md_path=md_path if md_path is not None else self.md_path,
            big_session_id=big_session_id or self.big_session_id,
            small_session_id=small_session_id or self.small_session_id,
        )

    def append(
        self,
        role: str,
        content: str,
        *,
        agent_key: str = "shared",
        turn_index: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Append one chat message and return its memory id."""
        memory_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(metadata or {}, ensure_ascii=False)

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO working_memory (
                    id, user_id, session_id, agent_key, role, content,
                    turn_index, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    self.user_id,
                    self.session_id,
                    agent_key,
                    role,
                    content,
                    turn_index,
                    created_at,
                    payload,
                ),
            )
            conn.commit()

        self.auto_compact()
        self._sync_md_after_append(role=role, agent_key=agent_key)
        return memory_id

    def _sync_md_after_append(self, *, role: str, agent_key: str) -> None:
        """Refresh the bound markdown context file with all agent outputs."""
        if self.md_path is None:
            return
        if role != "assistant" and role != "tool":
            return
        try:
            from ..memory_template_writer import AgentOutputRecord, update_memory_template
        except Exception:
            return

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_key, role, content
                FROM working_memory
                WHERE user_id = ? AND session_id = ?
                ORDER BY rowid ASC
                """,
                (self.user_id, self.session_id),
            ).fetchall()

        agent_outputs: list[AgentOutputRecord] = []
        tool_call_total = 0
        for row in rows:
            row_role = row["role"]
            row_agent = (row["agent_key"] or "").strip()
            if row_role == "assistant" and row_agent and row_agent != "shared":
                agent_outputs.append(
                    AgentOutputRecord(agent_name=row_agent, output=row["content"])
                )
            elif row_role == "tool":
                tool_call_total += 1

        try:
            update_memory_template(
                template_path=self.md_path,
                agent_outputs=agent_outputs,
                tool_call_total=tool_call_total,
            )
        except Exception:
            return

    def get_history(
        self,
        *,
        agent_key: str | None = None,
        include_shared: bool = True,
        limit: int | None = None,
    ) -> list[ChatMessage]:
        """Return messages in insertion order as model-ready chat messages."""
        where = ["user_id = ?", "session_id = ?"]
        params: list[Any] = [self.user_id, self.session_id]

        if agent_key is not None:
            if include_shared:
                where.append("(agent_key = ? OR agent_key = 'shared')")
            else:
                where.append("agent_key = ?")
            params.append(agent_key)

        sql = (
            "SELECT role, content FROM working_memory "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY rowid ASC"
        )
        if limit is not None and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)

        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            summary = self._get_compaction_state(conn)["summary"]

        history = [{"role": row["role"], "content": row["content"]} for row in rows]
        if summary:
            return [{"role": "system", "content": summary}, *history]
        return history

    def auto_compact(
        self,
        *,
        config: SessionMemoryCompactConfig | None = None,
    ) -> CompactionResult | None:
        """Run threshold-based context compaction for the current session."""
        with self._lock, self._connect() as conn:
            rows = self._get_session_rows(conn)
            messages = self._rows_to_compaction_messages(rows)
            state = self._get_compaction_state(conn)
            tracking = AutoCompactTrackingState(
                compacted=bool(state["summary"]),
                turn_counter=int(state["turn_counter"] or 0),
                turn_id=rows[-1]["id"] if rows else "",
                consecutive_failures=int(state["consecutive_failures"] or 0),
            )

            try:
                result = auto_compact_if_needed(
                    messages,
                    previous_summary=state["summary"],
                    last_summarized_id=state["last_summarized_id"],
                    tracking=tracking,
                    config=config,
                )
            except Exception:
                self._save_compaction_state(
                    conn,
                    summary=state["summary"],
                    last_summarized_id=state["last_summarized_id"],
                    consecutive_failures=tracking.consecutive_failures + 1,
                    turn_counter=tracking.turn_counter + 1,
                )
                conn.commit()
                return None

            if result is None:
                return None

            self._apply_compaction_result(conn, result)
            conn.commit()
            return result

    def compact_now(
        self,
        *,
        config: SessionMemoryCompactConfig | None = None,
    ) -> CompactionResult | None:
        """Manually compact the current session regardless of threshold."""
        from ._context_compaction import compact_conversation

        with self._lock, self._connect() as conn:
            rows = self._get_session_rows(conn)
            messages = self._rows_to_compaction_messages(rows)
            state = self._get_compaction_state(conn)
            result = compact_conversation(
                messages,
                previous_summary=state["summary"],
                last_summarized_id=state["last_summarized_id"],
                config=config,
            )
            if result is None:
                return None
            self._apply_compaction_result(conn, result)
            conn.commit()
            return result

    def token_warning_state(self) -> dict[str, Any]:
        """Return the same threshold state used by automatic compaction."""
        with self._lock, self._connect() as conn:
            messages = self._rows_to_compaction_messages(self._get_session_rows(conn))
            summary = self._get_compaction_state(conn)["summary"]
        threshold_messages = (
            [{"role": "system", "content": summary}]
            if summary
            else []
        ) + messages
        token_usage = estimate_message_tokens(threshold_messages)
        state = calculate_token_warning_state(token_usage)
        return {
            "token_usage": token_usage,
            "auto_compact_threshold": get_auto_compact_threshold(),
            "percent_left": state.percent_left,
            "is_above_warning_threshold": state.is_above_warning_threshold,
            "is_above_error_threshold": state.is_above_error_threshold,
            "is_above_auto_compact_threshold": (
                state.is_above_auto_compact_threshold
            ),
            "is_at_blocking_limit": state.is_at_blocking_limit,
        }

    def clear(self) -> int:
        """Clear current user/session memory and return deleted row count."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM working_memory WHERE user_id = ? AND session_id = ?",
                (self.user_id, self.session_id),
            )
            conn.execute(
                """
                DELETE FROM working_memory_compaction_state
                WHERE user_id = ? AND session_id = ?
                """,
                (self.user_id, self.session_id),
            )
            conn.commit()
            return cursor.rowcount

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS working_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    agent_key TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    turn_index INTEGER,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """,
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_working_memory_scope
                ON working_memory (user_id, session_id, agent_key)
                """,
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS working_memory_compaction_state (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    last_summarized_id TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    turn_counter INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, session_id)
                )
                """,
            )
            conn.commit()

    def _get_session_rows(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        return conn.execute(
            """
            SELECT id, agent_key, role, content, turn_index, created_at, metadata_json
            FROM working_memory
            WHERE user_id = ? AND session_id = ?
            ORDER BY rowid ASC
            """,
            (self.user_id, self.session_id),
        ).fetchall()

    def _rows_to_compaction_messages(
        self,
        rows: list[sqlite3.Row],
    ) -> list[dict[str, str]]:
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
            }
            for row in rows
        ]

    def _get_compaction_state(
        self,
        conn: sqlite3.Connection,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT summary, last_summarized_id, consecutive_failures, turn_counter
            FROM working_memory_compaction_state
            WHERE user_id = ? AND session_id = ?
            """,
            (self.user_id, self.session_id),
        ).fetchone()
        if row is None:
            return {
                "summary": "",
                "last_summarized_id": None,
                "consecutive_failures": 0,
                "turn_counter": 0,
            }
        return {
            "summary": row["summary"],
            "last_summarized_id": row["last_summarized_id"],
            "consecutive_failures": row["consecutive_failures"],
            "turn_counter": row["turn_counter"],
        }

    def _save_compaction_state(
        self,
        conn: sqlite3.Connection,
        *,
        summary: str,
        last_summarized_id: str | None,
        consecutive_failures: int,
        turn_counter: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO working_memory_compaction_state (
                user_id, session_id, summary, last_summarized_id,
                consecutive_failures, turn_counter, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, session_id) DO UPDATE SET
                summary = excluded.summary,
                last_summarized_id = excluded.last_summarized_id,
                consecutive_failures = excluded.consecutive_failures,
                turn_counter = excluded.turn_counter,
                updated_at = excluded.updated_at
            """,
            (
                self.user_id,
                self.session_id,
                summary,
                last_summarized_id,
                consecutive_failures,
                turn_counter,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def md_context_messages(self) -> list[ChatMessage]:
        """Return the bound markdown context as chat messages.

        Useful when callers want to expose the small-session context to the
        model directly (e.g. as a system primer). Returns an empty list if no
        markdown file is bound.
        """
        if self.md_path is None:
            return []
        return load_memory_context_messages(self.md_path)

    def _apply_compaction_result(
        self,
        conn: sqlite3.Connection,
        result: CompactionResult,
    ) -> None:
        keep_ids = {
            message["id"]
            for message in result.messages_to_keep
            if message.get("id")
        }
        if keep_ids:
            placeholders = ",".join("?" for _ in keep_ids)
            conn.execute(
                f"""
                DELETE FROM working_memory
                WHERE user_id = ? AND session_id = ?
                  AND id NOT IN ({placeholders})
                """,
                (self.user_id, self.session_id, *keep_ids),
            )
        else:
            conn.execute(
                """
                DELETE FROM working_memory
                WHERE user_id = ? AND session_id = ?
                """,
                (self.user_id, self.session_id),
            )

        state = self._get_compaction_state(conn)
        self._save_compaction_state(
            conn,
            summary=result.summary_message["content"],
            last_summarized_id=result.last_summarized_id,
            consecutive_failures=0,
            turn_counter=int(state["turn_counter"] or 0) + 1,
        )


def load_memory_context_messages(md_path: str | Path) -> list[ChatMessage]:
    """Parse a small-session markdown file into model-ready chat messages.

    The markdown file is the canonical small-session context: it contains the
    cumulative Agent outputs of the current 10-turn window. We expose it as a
    short list of ``ChatMessage`` so callers (typically generated flows) can
    inject it into the model prompt as a single ``system`` primer.
    """
    path = Path(md_path)
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    cleaned = text.strip()
    if not cleaned:
        return []
    return [{"role": "system", "content": cleaned}]


__all__ = [
    "AgentWorkingMemory",
    "ChatMessage",
    "load_memory_context_messages",
]
