from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypedDict


# back_agent 内部统一使用 OpenAI chat messages 形状，便于切换兼容模型服务。
class ChatMessage(TypedDict):
    role: str
    content: str


class ModelResponse(TypedDict, total=False):
    content: str


class BaseModel(ABC):
    """所有模型实现都应遵守的统一接口。"""

    @abstractmethod
    def set_stream_mode(self, stream: bool) -> None:
        # ReAct 调试时常用流式输出；测试或批处理时可以关闭。
        """设置默认流式输出模式。"""

    @abstractmethod
    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: Optional[bool] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """以消息数组方式调用模型。"""

    @abstractmethod
    def chat_with_system(
        self,
        system_message: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """以 system + user 快捷方式调用模型。"""

    @abstractmethod
    def get_model_name(self) -> str:
        """获取当前模型名称。"""
