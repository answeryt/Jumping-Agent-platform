from __future__ import annotations

import argparse
import os
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_AGENT_ID_DB_ENV = "AGENT_MANAGER_DB"
DEFAULT_AGENT_ID_DB = Path(__file__).resolve().parent / "agent_ids.sqlite3"
_AGENT_ID_PATTERN = re.compile(r"^agent-(\d{4,})$")


class AgentIdStore:
    """Persist stable runtime agent ids for generated agent names."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        override = os.getenv(DEFAULT_AGENT_ID_DB_ENV, "").strip()
        self.db_path = Path(db_path or override or DEFAULT_AGENT_ID_DB)
        self._lock = threading.RLock()
        self._ensure_schema()

    def get_or_create_agent_id(self, agent_name: str) -> str:
        name = self._normalize_agent_name(agent_name)
        now = self._utc_now()
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT agent_id FROM agent_ids WHERE agent_name = ?",
                (name,),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE agent_ids SET updated_at = ? WHERE agent_name = ?",
                    (now, name),
                )
                conn.commit()
                return str(row["agent_id"])

            agent_id = self._next_agent_id(conn)
            conn.execute(
                """
                INSERT INTO agent_ids (agent_name, agent_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, agent_id, now, now),
            )
            conn.commit()
            return agent_id

    def agent_name(self, agent_id: Optional[str]) -> Optional[str]:
        value = str(agent_id or "").strip()
        if not value:
            return None
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT agent_name FROM agent_ids WHERE agent_id = ?",
                (value,),
            ).fetchone()
        return str(row["agent_name"]) if row is not None else None

    def list_agents(self) -> list[dict[str, str]]:
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT agent_name, agent_id, created_at, updated_at
                FROM agent_ids
                ORDER BY agent_id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def register_many(self, agent_names: Iterable[str]) -> list[dict[str, str]]:
        registered = []
        for agent_name in agent_names:
            agent_id = self.get_or_create_agent_id(agent_name)
            registered.append({"agent_name": self._normalize_agent_name(agent_name), "agent_id": agent_id})
        return registered

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_ids (
                    agent_name TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _next_agent_id(self, conn: sqlite3.Connection) -> str:
        rows = conn.execute("SELECT agent_id FROM agent_ids").fetchall()
        max_index = 0
        for row in rows:
            match = _AGENT_ID_PATTERN.match(str(row["agent_id"]))
            if match:
                max_index = max(max_index, int(match.group(1)))
        return f"agent-{max_index + 1:04d}"

    @staticmethod
    def _normalize_agent_name(agent_name: str) -> str:
        name = str(agent_name or "").strip()
        if not name:
            raise ValueError("agent_name is required")
        return name

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist and inspect runtime agent ids.")
    parser.add_argument("agent_names", nargs="*", help="Agent names to register.")
    parser.add_argument("--db", dest="db_path", help="SQLite database path.")
    parser.add_argument("--list", action="store_true", help="List persisted agent ids.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    store = AgentIdStore(args.db_path)
    if args.agent_names:
        for item in store.register_many(args.agent_names):
            print(f"{item['agent_name']} {item['agent_id']}")
    if args.list or not args.agent_names:
        for item in store.list_agents():
            print(f"{item['agent_name']} {item['agent_id']}")


if __name__ == "__main__":
    main()
