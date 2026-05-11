from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from Agent.base_agent import BaseAgent, PromptLoader
from Model.base_model import BaseModel


@dataclass
class SummarizerAgentConfig:
    """SummarizerAgent 的运行参数。"""

    prompt_file: str = "summarizer_agent.md"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None
    max_retries: int = 2


class SummarizerAgent(BaseAgent):
    """
    负责"summarizer"的 agent。
    注意：提示词不写在代码里，只从 Prompt 文件读取。
    """

    def __init__(
        self,
        model: Optional[BaseModel] = None,
        config: Optional[SummarizerAgentConfig] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        super().__init__(
            agent_type="summarizer",
            model=model,
            config=config or SummarizerAgentConfig(),
            prompt_loader=prompt_loader,
        )

    def run(self, user_input: str, **kwargs) -> str:
        system_prompt = self.load_prompt()
        response = self.model.chat_with_system(
            system_message=system_prompt,
            user_message=user_input,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=self.config.stream,
        )
        return str(response.get("content", "")).strip()
