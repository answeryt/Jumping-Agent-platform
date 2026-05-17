from __future__ import annotations

import builtins
import contextlib
import io
import sys
from pathlib import Path
from typing import Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Model.base_model import BaseModel, ChatMessage, ModelResponse
from skill.skill_registry import get_skill
from workflow import run_react_agent as run_react_agent_module


class _ScriptedOpenAIModel(BaseModel):
    """用于替代 run_react_agent.py 中真实 OpenAIModel 的脚本化假模型。"""

    last_instance: "_ScriptedOpenAIModel | None" = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._stream = False
        self.message_snapshots: List[List[ChatMessage]] = []
        self.chat_calls = 0
        type(self).last_instance = self

    def set_stream_mode(self, stream: bool) -> None:
        self._stream = stream

    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        self.chat_calls += 1
        self.message_snapshots.append([dict(message) for message in messages])

        if self.chat_calls == 1:
            return {
                "content": (
                    "Thought: 这是一个包含 planner、researcher、writer 的多 agent 协作任务，需要明确上下游与 handoff。\n"
                    "Action: [SELECT_SKILL]multi-agent-skill[/SELECT_SKILL]"
                )
            }

        if self.chat_calls == 2:
            return {
                "content": (
                    "Final Answer: 已识别为多 agent 场景，并读取 multi-agent-skill 后再继续设计框架。"
                )
            }

        raise AssertionError(f"Unexpected extra model call: {self.chat_calls}")

    def chat_with_system(
        self,
        system_message: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        raise AssertionError("run_react_agent.run_cli() should use workflow chat(), not chat_with_system().")

    def get_model_name(self) -> str:
        return "scripted-openai-model"


def _run_cli_once() -> tuple[str, _ScriptedOpenAIModel]:
    original_input = builtins.input
    original_model_cls = run_react_agent_module.OpenAIModel

    scripted_inputs = iter(
        [
            "请帮我设计一个多agent框架，需要 planner、researcher、writer 三个角色，并说明上下游 handoff。",
            "/exit",
        ]
    )
    stdout_buffer = io.StringIO()

    def _fake_input(prompt: str = "") -> str:
        try:
            return next(scripted_inputs)
        except StopIteration as exc:
            raise EOFError from exc

    try:
        builtins.input = _fake_input
        run_react_agent_module.OpenAIModel = _ScriptedOpenAIModel
        with contextlib.redirect_stdout(stdout_buffer):
            run_react_agent_module.run_cli(max_context_turns=2)
    finally:
        builtins.input = original_input
        run_react_agent_module.OpenAIModel = original_model_cls

    model = _ScriptedOpenAIModel.last_instance
    if model is None:
        raise AssertionError("Scripted model was not instantiated.")
    return stdout_buffer.getvalue(), model


def main() -> None:
    print("=" * 72)
    print("TEST  调用 run_react_agent.py 验证 multi-agent-skill 动态加载")
    print("=" * 72)

    output, model = _run_cli_once()
    skill = get_skill("multi-agent-skill")

    if model.chat_calls != 2:
        raise AssertionError(f"Expected exactly 2 model calls, got {model.chat_calls}")

    if len(model.message_snapshots) != 2:
        raise AssertionError("Missing model message snapshots.")

    first_call_messages = model.message_snapshots[0]
    second_call_messages = model.message_snapshots[1]

    first_user_message = first_call_messages[1]["content"]
    second_last_message = second_call_messages[-1]["content"]

    assert "multi-agent-skill" in first_user_message, "Initial metadata context should expose multi-agent-skill name."
    assert "description:" in first_user_message, "Initial metadata context should only expose skill metadata."
    assert "# 多 Agent Skill" not in first_user_message, "Initial metadata phase should not reveal full skill body."

    assert "Observation: [SKILL_SELECTED] multi-agent-skill" in second_last_message
    assert "# 多 Agent Skill" in second_last_message, "Selected skill body should be injected on demand."
    assert "共享 contract 与 runtime 观察" in second_last_message
    assert "检查与收尾" in second_last_message
    assert "name: multi-agent-skill" not in second_last_message, "Front matter should be stripped before disclosure."
    assert skill.path.name in output or "multi-agent-skill" in output
    assert "Final Answer: 已识别为多 agent 场景" in output

    print("[PASS] run_react_agent.py 能根据任务动态加载 multi-agent-skill")
    print(f"[INFO] model_calls={model.chat_calls}")
    print(f"[INFO] disclosed_message_preview={second_last_message[:180]}...")


if __name__ == "__main__":
    main()
