"""
templates.py

存放所有 Agent 代码生成所需的模板。
create_agent.py 从这里导入，不在脚本中内嵌模板字符串。
"""

from __future__ import annotations


def agent_py(class_prefix: str, agent_type: str, prompt_file: str) -> str:
    """生成 Agent Python 文件内容。"""
    return f'''from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from Agent.base_agent import BaseAgent, PromptLoader
from Model.base_model import BaseModel


@dataclass
class {class_prefix}AgentConfig:
    """{class_prefix}Agent 的运行参数。"""

    prompt_file: str = "{prompt_file}"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None
    max_retries: int = 2


class {class_prefix}Agent(BaseAgent):
    """
    负责"{agent_type}"的 agent。
    注意：提示词不写在代码里，只从 Prompt 文件读取。
    """

    def __init__(
        self,
        model: Optional[BaseModel] = None,
        config: Optional[{class_prefix}AgentConfig] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        super().__init__(
            agent_type="{agent_type}",
            model=model,
            config=config or {class_prefix}AgentConfig(),
            prompt_loader=prompt_loader,
        )
'''


def prompt_md(class_prefix: str, agent_type: str) -> str:
    """生成 Prompt Markdown 文件内容。"""
    return f'''# {class_prefix} Agent 提示词

你是 {class_prefix} Agent，负责"{agent_type}"相关任务。

## 职责

- 在此描述该 agent 的核心职责

## 输出格式

请按以下结构输出：

- result: <本轮结果>
- next_agent: <下一个 agent，填 none 表示结束>
- next_task: <交给下一个 agent 的任务描述>
- steps: <本轮执行步骤>
- skills_used: none
- notes: <备注>
'''
