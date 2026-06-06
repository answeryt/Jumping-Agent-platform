from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    from .base_agent import BaseAgent, PromptLoader
    from ..Model.base_model import BaseModel
except ImportError:  # pragma: no cover - legacy top-level imports
    from agent.base_agent import BaseAgent, PromptLoader
    from Model.base_model import BaseModel


@dataclass
class ReactAgentConfig:
    """ReactAgent 的运行参数。"""

    prompt_file: str = "react_agent.md"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None
    max_retries: int = 2


class ReactAgent(BaseAgent):
    """
    基于 ReAct（Reasoning + Acting）范式的 agent。
    注意：提示词不写在代码里，只从 Prompt 文件读取。
    """

    def __init__(
        self,
        model: Optional[BaseModel] = None,
        config: Optional[ReactAgentConfig] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        # ReactAgent 自身不实现 run；真实运行逻辑在 workflow/_RuntimeReactAgent 中补齐。
        super().__init__(
            agent_type="react",
            model=model,
            config=config or ReactAgentConfig(),
            prompt_loader=prompt_loader,
        )
