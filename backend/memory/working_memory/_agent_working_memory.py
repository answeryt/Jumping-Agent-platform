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
from typing import Any

from ._context_compaction import (
    AutoCompactTrackingState,
    CompactionResult,
    SessionMemoryCompactConfig,
    auto_compact_if_needed,
    calculate_token_warning_state,
    estimate_message_tokens,
    get_auto_compact_threshold,
)

ChatMessage = dict[str, str]


class AgentWorkingMemory:
    """Persistent short-term memory shared by all generated agents."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        user_id: str = "default_user",
        session_id: str = "default_session",
    ) -> None:
        default_db = Path(__file__).resolve().parent / "working_memory.sqlite3"
        self.db_path = Path(
            db_path or os.getenv("AGENT_WORKING_MEMORY_DB") or default_db,
        )
        self.user_id = user_id
        self.session_id = session_id
        self._lock = threading.RLock()
        self._ensure_schema()

    def for_session(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> "AgentWorkingMemory":
        """Create a memory handle pointing at the same store."""
        return AgentWorkingMemory(
            self.db_path,
            user_id=user_id or self.user_id,
            session_id=session_id or self.session_id,
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
        return memory_id

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
