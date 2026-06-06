from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseFlow(ABC):
    """Flow 抽象基类：仅定义统一入口，不承载业务逻辑。"""

    def __init__(self, flow_type: str) -> None:
        # flow_type 用于日志、错误信息和工厂注册，不参与具体执行。
        self.flow_type = flow_type

    @abstractmethod
    def run(self, user_input: str, **kwargs: Any) -> str:
        """执行 flow 主流程并返回文本结果。"""

    def __call__(self, user_input: str, **kwargs: Any) -> str:
        # 允许把 flow 实例当函数用，实际仍然转发到 run。
        return self.run(user_input, **kwargs)
