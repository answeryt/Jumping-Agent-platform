from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class PromptLoader:
    """从文件系统加载提示词。"""

    def __init__(self, prompt_dir: Optional[Path] = None) -> None:
        self.prompt_dir = prompt_dir or Path(__file__).resolve().parent.parent / "prompts"

    def load(self, filename: str) -> str:
        path = self.prompt_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"提示词文件不存在: {path}")
        return path.read_text(encoding="utf-8")


class BaseAgent(ABC):
    """所有 Agent 实现都应遵守的统一接口。"""

    def __init__(
        self,
        agent_type: str,
        model: Any = None,
        config: Any = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        self.agent_type = agent_type
        self.model = model
        self.config = config
        self.prompt_loader = prompt_loader or PromptLoader()

    def load_prompt(self) -> str:
        """根据 config.prompt_file 加载系统提示词。"""
        return self.prompt_loader.load(self.config.prompt_file)

    @abstractmethod
    def run(self, user_input: str, **kwargs: Any) -> str:
        """执行 agent 的主逻辑，返回响应文本。"""
