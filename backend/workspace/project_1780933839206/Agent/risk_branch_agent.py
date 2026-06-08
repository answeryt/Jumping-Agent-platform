from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from Agent.base_agent import BaseAgent, PromptLoader
from Model.base_model import BaseModel


@dataclass
class RiskBranchAgentConfig:
    """RiskBranchAgent 的运行参数。"""

    prompt_file: str = "risk_branch_agent.md"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None
    max_retries: int = 2


class RiskBranchAgent(BaseAgent):
    """
    负责"risk_branch"的 agent。
    注意：提示词不写在代码里，只从 Prompt 文件读取。
    """

    def __init__(
        self,
        model: Optional[BaseModel] = None,
        config: Optional[RiskBranchAgentConfig] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        super().__init__(
            agent_type="risk_branch",
            model=model,
            config=config or RiskBranchAgentConfig(),
            prompt_loader=prompt_loader,
        )

    def run(self, user_input: str, **kwargs: Any) -> str:
        """执行单轮 agent 调用，保留统一的基础运行契约。"""
        if self.model is None:
            raise ValueError("agent model is required")
        system_prompt = self.load_prompt()
        model_kwargs = dict(kwargs)
        model_kwargs.pop("history", None)
        runtime_system_prompt = str(model_kwargs.pop("runtime_system_prompt", "") or "").strip()
        if runtime_system_prompt:
            system_prompt = f"{system_prompt}

{runtime_system_prompt}"
        response = self.model.chat_with_system(
            system_message=system_prompt,
            user_message=user_input,
            temperature=getattr(self.config, "temperature", None),
            max_tokens=getattr(self.config, "max_tokens", None),
            stream=getattr(self.config, "stream", None),
            **model_kwargs,
        )
        return str(response.get("content", "")).strip()
