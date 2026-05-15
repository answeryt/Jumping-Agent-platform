# -*- coding: utf-8 -*-
"""Minimal base types for backend working memory."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


class StateModule:
    """Small state helper compatible with the copied memory implementations."""

    def __init__(self) -> None:
        self._state_keys: list[str] = []

    def register_state(self, key: str) -> None:
        if key not in self._state_keys:
            self._state_keys.append(key)

    def state_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self._state_keys}


@dataclass
class Msg:
    """Serializable chat message used by the async memory backend."""

    name: str
    content: Any
    role: str
    id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Msg":
        return cls(
            name=data.get("name", data.get("role", "")),
            content=data.get("content", ""),
            role=data.get("role", data.get("name", "")),
            id=data.get("id") or str(uuid4()),
        )


class MemoryBase(StateModule):
    """The base class for short-term memory backends."""

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    async def add(
        self,
        memories: Msg | list[Msg] | None,
        marks: str | list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Add message(s) into memory."""

    @abstractmethod
    async def delete(self, msg_ids: list[str], **kwargs: Any) -> int:
        """Remove message(s) from memory by ids."""

    async def delete_by_mark(
        self,
        mark: str | list[str],
        *args: Any,
        **kwargs: Any,
    ) -> int:
        raise NotImplementedError(
            "The delete_by_mark method is not implemented in "
            f"{self.__class__.__name__} class.",
        )

    @abstractmethod
    async def size(self) -> int:
        """Get message count."""

    @abstractmethod
    async def clear(self) -> None:
        """Clear memory content."""

    @abstractmethod
    async def get_memory(
        self,
        mark: str | None = None,
        exclude_mark: str | None = None,
        prepend_summary: bool = True,
        **kwargs: Any,
    ) -> list[Msg]:
        """Get messages from memory."""

    async def update_messages_mark(
        self,
        new_mark: str | None,
        old_mark: str | None = None,
        msg_ids: list[str] | None = None,
    ) -> int:
        raise NotImplementedError(
            "The update_messages_mark method is not implemented in "
            f"{self.__class__.__name__} class.",
        )
