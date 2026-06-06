from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel as PydanticModel
from starlette.concurrency import run_in_threadpool

from agent.base_agent import PromptLoader
from agent.react import ReactAgentConfig
from Model.oepai import OpenAIModel
from workflow.flow_factory import FlowFactory

# ---------------------------------------------------------------------------
# 初始化 flow（单例，服务启动时创建一次）
# ---------------------------------------------------------------------------

# API 层只持有一个 ReAct flow 实例；所有 /chat 请求复用同一套模型、prompt 和工具注册。
_flow: Optional[Any] = None

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(title="ReactAgent API")


def _get_flow() -> Any:
    global _flow
    if _flow is not None:
        return _flow

    model = OpenAIModel()
    prompt_loader = PromptLoader(prompt_dir=PROJECT_ROOT / "prompt")
    agent_config = ReactAgentConfig(prompt_file="react_agent_prompt.md")
    _flow = FlowFactory.create(
        "react",
        model=model,
        agent_config=agent_config,
        prompt_loader=prompt_loader,
    )
    return _flow


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
    # back_agent 不管理持久化 session；backend 传来的 history 会在这里压成普通文本。
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
    # FastAPI 入口很薄：组装上下文 -> 运行 ReAct flow -> 返回 answer。
    history: List[Tuple[str, str]] = (
        [(item.human, item.assistant) for item in request.history]
        if request.history
        else []
    )
    merged_input = _build_user_input(history=history, user_text=request.user_input)
    try:
        flow = _get_flow()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"back_agent is not ready: {exc}",
        ) from exc
    answer = await run_in_threadpool(flow.run, merged_input)
    return ChatResponse(answer=answer)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
