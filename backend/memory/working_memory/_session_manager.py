# -*- coding: utf-8 -*-
"""Two-tier session manager for backend working memory.

Concepts:
- big session: one chat panel in the UI. Stays the same until the user clicks
  "new chat" in the frontend.
- small session: a 10-turn window inside a big session. Each small session owns
  exactly one markdown context file (cloned from
  ``backend/memory/memory_templete.md``) into which every Agent output of those
  10 turns is appended.

A single small session may invoke many agents per user turn (e.g. a Sequential
flow with 5 agents), but the turn counter only advances when a new user request
arrives. When the counter reaches the rotation threshold the next user request
is automatically bound to a fresh small session md inside the same big session
directory; cross-big-session traffic stays fully isolated.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_SESSIONS_ROOT_ENV = "AGENT_MEMORY_SESSIONS_ROOT"
MAX_TURNS_PER_SMALL_SESSION = 10


@dataclass(frozen=True)
class SmallSessionBinding:
    """Resolved binding for the small session currently in use."""

    big_session_id: str
    small_session_id: str
    md_path: Path
    turns_used: int

    @property
    def composite_session_id(self) -> str:
        """Composite id stored on SQLite rows; keeps big/small in one string."""
        return f"{self.big_session_id}/{self.small_session_id}"


@dataclass(frozen=True)
class MemorySessionContext:
    """运行时传给 memory 的唯一会话对象，避免到处散传 user/session 参数。"""

    user_id: str
    session_id: str
    big_session_id: str | None = None
    small_session_id: str | None = None
    md_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("MemorySessionContext.user_id is required")
        if not self.session_id:
            raise ValueError("MemorySessionContext.session_id is required")

    @classmethod
    def from_binding(
        cls,
        *,
        user_id: str,
        binding: SmallSessionBinding,
    ) -> "MemorySessionContext":
        return cls(
            user_id=user_id,
            session_id=binding.composite_session_id,
            big_session_id=binding.big_session_id,
            small_session_id=binding.small_session_id,
            md_path=binding.md_path,
        )


def _default_sessions_root() -> Path:
    override = os.getenv(DEFAULT_SESSIONS_ROOT_ENV, "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "sessions"


def _short_token() -> str:
    return uuid.uuid4().hex[:8]


def _short_timestamp() -> str:
    return time.strftime("%Y%m%d%H%M%S")


def _safe_id(value: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value or "")
    cleaned = cleaned.strip("_") or fallback
    return cleaned


class SessionManager:
    """Resolve big/small session ids and the markdown files behind them.

    Persistence is intentionally lightweight: each big session directory keeps
    a sidecar ``index.json`` so reconstruction across process restarts is
    cheap. SQLite is the authoritative store for chat rows; this manager only
    decides *which* md file the current chat belongs to.
    """

    def __init__(
        self,
        sessions_root: str | Path | None = None,
        *,
        max_turns_per_small_session: int = MAX_TURNS_PER_SMALL_SESSION,
    ) -> None:
        self.sessions_root = Path(sessions_root) if sessions_root else _default_sessions_root()
        self.max_turns_per_small_session = max(1, int(max_turns_per_small_session))
        self._lock = threading.RLock()

    def start_big_session(self, big_session_id: Optional[str] = None) -> str:
        """Allocate a new big session directory and return its id."""
        with self._lock:
            base = _safe_id(big_session_id or "", fallback="")
            if base:
                resolved = base
                attempt = 1
                while (self.sessions_root / resolved).exists():
                    attempt += 1
                    resolved = f"{base}_{attempt}"
            else:
                resolved = f"big_{_short_timestamp()}_{_short_token()}"
            big_dir = self.sessions_root / resolved
            big_dir.mkdir(parents=True, exist_ok=True)
            self._write_index(big_dir, self._empty_index(resolved))
            return resolved

    def resolve_big_session(self, big_session_id: Optional[str]) -> str:
        """Return an existing big session id, creating one if necessary."""
        candidate = _safe_id(big_session_id or "", fallback="")
        if candidate and (self.sessions_root / candidate).exists():
            return candidate
        return self.start_big_session(candidate or None)

    def pick_or_create_small_session(
        self,
        big_session_id: str,
        *,
        template_path: str | Path | None = None,
    ) -> SmallSessionBinding:
        """Return the small session this chat turn should be bound to.

        - If the current small session has fewer than ``max_turns_per_small_session``
          user turns, reuse it.
        - Otherwise allocate a new small session md inside the same big session.
        """
        with self._lock:
            big_dir = self.sessions_root / _safe_id(big_session_id, fallback="big_unknown")
            big_dir.mkdir(parents=True, exist_ok=True)
            index = self._read_index(big_dir, big_session_id)

            current = index.get("current_small")
            if current and int(current.get("turns_used", 0)) < self.max_turns_per_small_session:
                md_path = Path(current["md_path"])
                if not md_path.is_absolute():
                    md_path = (big_dir / md_path).resolve()
                if md_path.exists():
                    return SmallSessionBinding(
                        big_session_id=big_session_id,
                        small_session_id=str(current["small_session_id"]),
                        md_path=md_path,
                        turns_used=int(current["turns_used"]),
                    )

            next_index = int(index.get("next_small_index", 1))
            small_session_id = f"small_{next_index:03d}_{_short_timestamp()}_{_short_token()}"
            md_path = (big_dir / f"{small_session_id}.md").resolve()
            self._ensure_md_from_template(md_path, template_path)

            entry = {
                "small_session_id": small_session_id,
                "md_path": str(md_path),
                "turns_used": 0,
                "created_at": time.time(),
            }
            small_sessions = list(index.get("small_sessions", []))
            small_sessions.append(entry)
            index["small_sessions"] = small_sessions
            index["current_small"] = dict(entry)
            index["next_small_index"] = next_index + 1
            self._write_index(big_dir, index)

            return SmallSessionBinding(
                big_session_id=big_session_id,
                small_session_id=small_session_id,
                md_path=md_path,
                turns_used=0,
            )

    def bind_memory_context(
        self,
        *,
        user_id: str,
        big_session_id: str,
        small_session_id: str | None = None,
        template_path: str | Path | None = None,
    ) -> MemorySessionContext:
        """把一次 UI 会话绑定成 memory 可直接使用的上下文对象。"""
        if small_session_id:
            big_dir = self.big_session_dir(big_session_id)
            md_path = big_dir / f"{small_session_id}.md"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_md_from_template(md_path, template_path)
            binding = SmallSessionBinding(
                big_session_id=big_session_id,
                small_session_id=small_session_id,
                md_path=md_path,
                turns_used=0,
            )
        else:
            binding = self.pick_or_create_small_session(
                big_session_id,
                template_path=template_path,
            )
        return MemorySessionContext.from_binding(user_id=user_id, binding=binding)

    def record_user_turn(self, binding: SmallSessionBinding) -> SmallSessionBinding:
        """Mark that one user turn was consumed in the bound small session."""
        with self._lock:
            big_dir = self.sessions_root / _safe_id(binding.big_session_id, fallback="big_unknown")
            index = self._read_index(big_dir, binding.big_session_id)
            current = index.get("current_small") or {}
            if str(current.get("small_session_id", "")) != binding.small_session_id:
                return binding
            new_count = int(current.get("turns_used", 0)) + 1
            current["turns_used"] = new_count
            for entry in index.get("small_sessions", []):
                if entry.get("small_session_id") == binding.small_session_id:
                    entry["turns_used"] = new_count
                    break
            index["current_small"] = current
            self._write_index(big_dir, index)
            return SmallSessionBinding(
                big_session_id=binding.big_session_id,
                small_session_id=binding.small_session_id,
                md_path=binding.md_path,
                turns_used=new_count,
            )

    def list_small_sessions(self, big_session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            big_dir = self.sessions_root / _safe_id(big_session_id, fallback="big_unknown")
            if not big_dir.exists():
                return []
            index = self._read_index(big_dir, big_session_id)
            return list(index.get("small_sessions", []))

    def big_session_dir(self, big_session_id: str) -> Path:
        return self.sessions_root / _safe_id(big_session_id, fallback="big_unknown")

    def _ensure_md_from_template(
        self,
        md_path: Path,
        template_path: str | Path | None,
    ) -> None:
        if md_path.exists():
            return
        from ..memory_template_writer import create_session_memory_template

        create_session_memory_template(template_path=template_path, dest_path=md_path)

    def _empty_index(self, big_session_id: str) -> dict[str, Any]:
        return {
            "big_session_id": big_session_id,
            "created_at": time.time(),
            "next_small_index": 1,
            "current_small": None,
            "small_sessions": [],
        }

    def _index_path(self, big_dir: Path) -> Path:
        return big_dir / "index.json"

    def _read_index(self, big_dir: Path, big_session_id: str) -> dict[str, Any]:
        path = self._index_path(big_dir)
        if not path.exists():
            return self._empty_index(big_session_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_index(big_session_id)

    def _write_index(self, big_dir: Path, index: dict[str, Any]) -> None:
        big_dir.mkdir(parents=True, exist_ok=True)
        path = self._index_path(big_dir)
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = [
    "DEFAULT_SESSIONS_ROOT_ENV",
    "MAX_TURNS_PER_SMALL_SESSION",
    "MemorySessionContext",
    "SessionManager",
    "SmallSessionBinding",
]
