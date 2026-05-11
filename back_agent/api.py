from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from pydantic import BaseModel as PydanticModel

from agent.base_agent import PromptLoader
from agent.react import ReactAgentConfig
from Model.oepai import OpenAIModel
from workflow.flow_factory import FlowFactory

# ---------------------------------------------------------------------------
# 初始化 flow（单例，服务启动时创建一次）
# ---------------------------------------------------------------------------

_model = OpenAIModel()
_prompt_loader = PromptLoader(prompt_dir=PROJECT_ROOT / "prompt")
_agent_config = ReactAgentConfig(prompt_file="react_agent_prompt.md")
_flow = FlowFactory.create(
    "react",
    model=_model,
    agent_config=_agent_config,
    prompt_loader=_prompt_loader,
)

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(title="ReactAgent API")


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------

class HistoryItem(PydanticModel):
    human: str
    assistant: str


class ChatRequest(PydanticModel):
    user_input: str
    history: Optional[List[HistoryItem]] = None
    agent_id: Optional[str] = None


class ChatResponse(PydanticModel):
    answer: str


# ---------------------------------------------------------------------------
# 唯一接口
# ---------------------------------------------------------------------------

def _build_user_input(history: List[Tuple[str, str]], user_text: str) -> str:
    """将完整对话历史拼接到当前输入中（无轮数上限）。"""
    if not history:
        return user_text

    lines: List[str] = ["以下是完整对话上下文："]
    for human, assistant in history:
        lines.append(f"用户: {human}")
        lines.append(f"助手: {assistant}")
    lines.append("请在保持上下文一致的前提下，继续回答用户最新问题。")
    lines.append(f"用户最新输入: {user_text}")
    return "\n".join(lines)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    history: List[Tuple[str, str]] = (
        [(item.human, item.assistant) for item in request.history]
        if request.history
        else []
    )
    merged_input = _build_user_input(history=history, user_text=request.user_input)
    answer = _flow.run(merged_input)
    return ChatResponse(answer=answer)
