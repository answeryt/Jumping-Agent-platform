# -*- coding: utf-8 -*-
"""Unified SQLite-backed long-term memory for generated agents."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..working_memory import Msg
from ._long_term_memory_base import LongTermMemoryBase, TextBlock, ToolResponse


class AgentLongTermMemory(LongTermMemoryBase):
    """Persistent long-term memory shared by all generated agents.

    The storage backend is intentionally the same family as AgentWorkingMemory:
    SQLite by default, with a path override through environment variables.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        user_id: str = "default_user",
        agent_id: str = "shared",
        project_id: str = "default_project",
    ) -> None:
        super().__init__()
        default_db = (
            Path(__file__).resolve().parent.parent
            / "working_memory"
            / "working_memory.sqlite3"
        )
        self.db_path = Path(
            db_path
            or os.getenv("AGENT_LONG_TERM_MEMORY_DB")
            or os.getenv("AGENT_WORKING_MEMORY_DB")
            or default_db,
        )
        self.user_id = user_id
        self.agent_id = agent_id
        self.project_id = project_id
        self._lock = threading.RLock()
        self._ensure_schema()

    def for_scope(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
    ) -> "AgentLongTermMemory":
        """Create a memory handle pointing at the same store."""
        return AgentLongTermMemory(
            self.db_path,
            user_id=user_id or self.user_id,
            agent_id=agent_id or self.agent_id,
            project_id=project_id or self.project_id,
        )

    async def record(
        self,
        msgs: list[Msg | None],
        memory_type: str = "general",
        **kwargs: Any,
    ) -> list[str]:
        """Record messages as long-term memory items."""
        ids: list[str] = []
        for msg in msgs:
            if msg is None:
                continue
            ids.append(
                self.add_memory(
                    str(msg.content),
                    memory_type=memory_type,
                    source="record",
                    metadata={"role": msg.role, **kwargs},
                ),
            )
        return ids

    async def retrieve(
        self,
        msg: Msg | list[Msg] | None,
        limit: int = 5,
        **kwargs: Any,
    ) -> str:
        """Retrieve memories relevant to one or more messages."""
        if msg is None:
            return ""
        msg_list = msg if isinstance(msg, list) else [msg]
        keywords = [str(item.content) for item in msg_list if item is not None]
        return "\n".join(self.search(keywords, limit=limit, **kwargs))

    async def record_to_memory(
        self,
        thinking: str,
        content: list[str],
        memory_type: str = "general",
        **kwargs: Any,
    ) -> ToolResponse:
        """Record important facts or reusable experience."""
        ids: list[str] = []
        if thinking:
            ids.append(
                self.add_memory(
                    thinking,
                    memory_type=memory_type,
                    source="thinking",
                    metadata=kwargs,
                ),
            )
        for item in content:
            item_text = str(item).strip()
            if not item_text:
                continue
            ids.append(
                self.add_memory(
                    item_text,
                    memory_type=memory_type,
                    source="tool",
                    metadata=kwargs,
                ),
            )

        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Successfully recorded {len(ids)} long-term memory item(s).",
                ),
            ],
            metadata={"memory_ids": ids},
        )

    async def retrieve_from_memory(
        self,
        keywords: list[str],
        limit: int = 5,
        **kwargs: Any,
    ) -> ToolResponse:
        """Retrieve long-term memories by keywords."""
        results = self.search(keywords, limit=limit, **kwargs)
        text = "\n".join(results) if results else "No long-term memories found."
        return ToolResponse(content=[TextBlock(type="text", text=text)])

    def add_memory(
        self,
        content: str,
        *,
        memory_type: str = "general",
        source: str = "manual",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 1.0,
    ) -> str:
        """Insert one long-term memory item."""
        memory_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        normalized_tags = tags or []
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        tags_json = json.dumps(normalized_tags, ensure_ascii=False)

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO long_term_memory (
                    id, user_id, project_id, agent_id, memory_type, content,
                    source, tags_json, importance, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    self.user_id,
                    self.project_id,
                    self.agent_id,
                    memory_type,
                    content,
                    source,
                    tags_json,
                    importance,
                    created_at,
                    metadata_json,
                ),
            )
            conn.commit()

        return memory_id

    def search(
        self,
        keywords: list[str],
        *,
        limit: int = 5,
        memory_type: str | None = None,
        include_shared: bool = True,
    ) -> list[str]:
        """Search long-term memories using simple scoped keyword matching."""
        cleaned_keywords = [kw.strip() for kw in keywords if str(kw).strip()]
        if not cleaned_keywords:
            return []

        where = ["user_id = ?", "project_id = ?"]
        params: list[Any] = [self.user_id, self.project_id]

        if include_shared:
            where.append("(agent_id = ? OR agent_id = 'shared')")
        else:
            where.append("agent_id = ?")
        params.append(self.agent_id)

        if memory_type:
            where.append("memory_type = ?")
            params.append(memory_type)

        keyword_clauses = []
        for keyword in cleaned_keywords:
            keyword_clauses.append("(content LIKE ? OR tags_json LIKE ?)")
            like_value = f"%{keyword}%"
            params.extend([like_value, like_value])
        where.append("(" + " OR ".join(keyword_clauses) + ")")

        sql = (
            "SELECT content FROM long_term_memory "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY importance DESC, rowid DESC "
            "LIMIT ?"
        )
        params.append(max(1, limit))

        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [row["content"] for row in rows]

    def clear(self) -> int:
        """Clear current user/project/agent long-term memories."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM long_term_memory
                WHERE user_id = ? AND project_id = ? AND agent_id = ?
                """,
                (self.user_id, self.project_id, self.agent_id),
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
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """,
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_long_term_memory_scope
                ON long_term_memory (user_id, project_id, agent_id, memory_type)
                """,
            )
            conn.commit()
