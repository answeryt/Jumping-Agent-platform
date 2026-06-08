from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, TypedDict


class ChatMessage(TypedDict):
    role: str
    content: str


class BaseModel(ABC):
    @abstractmethod
    def chat_with_system(self, system_message: str, user_message: str, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_model_name(self) -> str:
        raise NotImplementedError
