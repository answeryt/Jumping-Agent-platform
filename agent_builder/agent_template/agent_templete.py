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
from typing import Any, Optional

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

    def run(self, user_input: str, **kwargs: Any) -> str:
        """执行单轮 agent 调用，保留统一的基础运行契约。"""
        if self.model is None:
            raise ValueError("agent model is required")
        system_prompt = self.load_prompt()
        model_kwargs = dict(kwargs)
        model_kwargs.pop("history", None)
        runtime_system_prompt = str(model_kwargs.pop("runtime_system_prompt", "") or "").strip()
        if runtime_system_prompt:
            system_prompt = f"{{system_prompt}}\n\n{{runtime_system_prompt}}"
        response = self.model.chat_with_system(
            system_message=system_prompt,
            user_message=user_input,
            temperature=getattr(self.config, "temperature", None),
            max_tokens=getattr(self.config, "max_tokens", None),
            stream=getattr(self.config, "stream", None),
            **model_kwargs,
        )
        return str(response.get("content", "")).strip()
'''


def prompt_md(class_prefix: str, agent_type: str) -> str:
    """生成 Prompt Markdown 文件内容。"""
    return f'''# {class_prefix} Agent 提示词

你是 {class_prefix} Agent，负责"{agent_type}"相关任务。

## 职责

- 在此描述该 agent 的核心职责

## 输出契约

你的输出分为两个通道，必须严格遵守：

1. 先输出面向用户或上游 agent 的自然语言正文，这部分可以被实时流式展示。
2. 在正文结束后，单独输出一行 `<<<CONTROL>>>`。
3. 在 `<<<CONTROL>>>` 之后，输出一个 JSON 对象，供 flow / runtime 解析。

控制 JSON 只包含 flow / runtime 需要的控制字段：

- `result`: <本轮核心结果摘要>
- `next_agent`: <下一个 agent，没有则 "none">
- `next_task`: <交接任务，没有则 "none">
- `should_stop`: <true 或 false>

示例：

我已经完成初步分析，建议下一步进入后端实现阶段。
<<<CONTROL>>>
{{
  "result": "完成需求分析并给出下一步建议",
  "next_agent": "backend_coder",
  "next_task": "实现接口与数据处理逻辑",
  "should_stop": false
}}

不要额外输出 goal、user_request、known_info、phase、constraints、steps、skills_used、notes 等上下文字段；上下文信息统一写入 MD blackboard。
'''
