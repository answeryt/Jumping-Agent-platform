from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.base_agent import PromptLoader
from agent.react import ReactAgentConfig
from Model.oepai import OpenAIModel
from workflow.flow_factory import FlowFactory


def build_flow():
    model = OpenAIModel()
    prompt_loader = PromptLoader(prompt_dir=PROJECT_ROOT / "prompt")
    agent_config = ReactAgentConfig(prompt_file="react_agent_prompt.md")
    return FlowFactory.create(
        "react",
        model=model,
        agent_config=agent_config,
        prompt_loader=prompt_loader,
    )


def _build_user_input(history: List[Tuple[str, str]], user_text: str, max_turns: int) -> str:
    """将最近 N 轮对话拼接到当前输入中，支持多轮上下文。"""
    if max_turns <= 0 or not history:
        return user_text

    sliced = history[-max_turns:]
    lines: List[str] = ["以下是最近对话上下文："]
    for human, assistant in sliced:
        lines.append(f"用户: {human}")
        lines.append(f"助手: {assistant}")
    lines.append("请在保持上下文一致的前提下，继续回答用户最新问题。")
    lines.append(f"用户最新输入: {user_text}")
    return "\n".join(lines)


def run_once(user_text: str, history: List[Tuple[str, str]] | None = None, max_context_turns: int = 6) -> str:
    """单次执行 React workflow，供后端直接调用。"""
    flow = build_flow()
    merged_input = _build_user_input(history=history or [], user_text=user_text, max_turns=max_context_turns)
    return flow.run(merged_input)


def run_cli(max_context_turns: int = 6) -> None:
    """ReactAgent 启动入口：仅做初始化、会话循环与输出。"""
    flow = build_flow()
    history: List[Tuple[str, str]] = []

    print("ReactAgent 已启动，输入 /exit 退出，输入 /clear 清空会话。")
    while True:
        user_text = input("\n你: ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"/exit", "exit", "quit", "/quit"}:
            print("会话结束。")
            break
        if user_text.lower() in {"/clear", "clear"}:
            history.clear()
            print("会话历史已清空。")
            continue

        merged_input = _build_user_input(history=history, user_text=user_text, max_turns=max_context_turns)
        try:
            answer = flow.run(merged_input)
        except Exception as exc:
            print(f"助手: 调用失败 -> {exc}")
            continue

        print(f"助手: {answer}")
        history.append((user_text, answer))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 ReactAgent 多轮对话脚本")
    parser.add_argument(
        "--max-context-turns",
        type=int,
        default=6,
        help="注入到当前轮中的历史对话轮数（默认 6）",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_cli(max_context_turns=args.max_context_turns)
