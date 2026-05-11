"""
单一 Agent 框架（单文件自包含）

- ReAct 循环：Thought → Action / Final Answer → Observation → …
- 可插拔 LLM：实现 LLMClient 协议即可
- 工具注册表：名称 + 描述 + 可调用对象，由模型按约定格式选用

约定输出格式（与常见 ReAct 提示词兼容）::

    Thought: ...
    Action: tool_name
    Action Input: ...

    或

    Thought: ...
    Final Answer: ...

运行示例::

    python system_test/test_react_agent.py
"""
from __future__ import annotations

# ── 版本标记（供集成测试验证 agent 代码改写能力，勿手动修改）
_AGENT_VERSION = "1.0.1-rewritten"

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Tuple, Union


# ─── 类型与协议 ────────────────────────────────────────────────────────────────


class LLMClient(Protocol):
    """可替换的模型后端：传入 OpenAI 风格 messages，返回一条 assistant 文本。"""

    def chat(self, messages: List[Dict[str, str]], *, temperature: float = 0.2) -> str: ...


ToolFn = Callable[[str], str]


@dataclass
class ToolSpec:
    name: str
    description: str
    run: ToolFn


@dataclass
class AgentConfig:
    max_steps: int = 8
    temperature: float = 0.2


@dataclass
class _FinalAnswer:
    text: str


@dataclass
class _Action:
    name: str
    action_input: str


# ─── 解析：从模型输出中提取 Final Answer 或 Action ────────────────────────────


_FINAL_ANSWER = re.compile(
    r"(?is)Final\s*Answer\s*:\s*(.*)",
)
_ACTION_BLOCK = re.compile(
    r"(?is)Action\s*:\s*([^\n]+?)\s*\n\s*Action\s*Input\s*:\s*(.*?)(?=\n\s*(?:Thought|Action|Final\s*Answer)\s*:|$)",
)


def _parse_step(text: str) -> Union[_FinalAnswer, _Action, None]:
    """从单轮模型输出中解析终止答案或一次工具调用。"""
    t = text.strip()
    if not t:
        return None

    fa = _FINAL_ANSWER.search(t)
    if fa:
        ans = fa.group(1).strip()
        # 若后面误贴了 Thought，截断到下一个段落标题
        for stop in ("\nThought:", "\nAction:", "\nFinal Answer:"):
            if stop.lower() in ans.lower():
                idx = ans.lower().find(stop.lower())
                ans = ans[:idx].strip()
        return _FinalAnswer(ans)

    ac = _ACTION_BLOCK.search(t)
    if ac:
        name = ac.group(1).strip()
        inp = ac.group(2).strip()
        return _Action(name=name, action_input=inp)

    return None


def _build_system_prompt(tools: Dict[str, ToolSpec]) -> str:
    lines = [
        "你是一个使用 ReAct 范式的助手：先思考，再选择工具或给出最终答案。",
        "每次回复必须严格使用下面两种格式之一（二选一）：",
        "",
        "【格式 A — 需要调用工具】",
        "Thought: 你的推理。",
        "Action: 工具名称（必须是下列之一）",
        "Action Input: 传给工具的输入（单行或多行均可）",
        "",
        "【格式 B — 已足够回答用户】",
        "Thought: 你的推理。",
        "Final Answer: 给用户的完整回答。",
        "",
        "可用工具：",
    ]
    for spec in tools.values():
        lines.append(f"- {spec.name}: {spec.description}")
    lines.append("")
    lines.append("不要编造工具名；若无需工具，直接用 Final Answer 结束。")
    return "\n".join(lines)


# ─── 单一 Agent 主体 ───────────────────────────────────────────────────────────


class SingleReactAgent:
    """
    单一 ReAct Agent：维护对话 messages，在循环中调用 LLM、解析、执行工具。
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: Dict[str, ToolSpec],
        *,
        config: Optional[AgentConfig] = None,
    ) -> None:
        self._llm = llm
        self._tools = dict(tools)
        self._config = config or AgentConfig()
        self._system = _build_system_prompt(self._tools)

    def run(self, user_task: str) -> str:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._system},
            {"role": "user", "content": user_task},
        ]

        for step in range(self._config.max_steps):
            raw = self._llm.chat(messages, temperature=self._config.temperature)
            parsed = _parse_step(raw)

            if isinstance(parsed, _FinalAnswer):
                return parsed.text

            if isinstance(parsed, _Action):
                if parsed.name not in self._tools:
                    obs = f"错误：未知工具 {parsed.name!r}。请从可用工具中选择。"
                else:
                    try:
                        obs = self._tools[parsed.name].run(parsed.action_input)
                    except Exception as exc:  # noqa: BLE001 — 工具错误回传给模型
                        obs = f"工具执行错误: {exc}"

                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Observation: {obs}",
                    },
                )
                continue

            # 无法解析：把原文当作需要纠正的轮次
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Observation: 无法解析你的上一段输出。"
                        "请严格使用 Thought + (Action / Action Input) 或 Thought + Final Answer。"
                    ),
                },
            )

        return "已达到最大步数，未得到 Final Answer。"


# ─── 内置示例：假模型（无网络、用于演示框架）──────────────────────────────────


class StubLLM:
    """
    确定性假 LLM：根据轮次返回 Action 或 Final Answer，便于本地跑通管线。
    """

    def __init__(self, plan: List[str]) -> None:
        self._plan = list(plan)
        self._i = 0

    def chat(self, messages: List[Dict[str, str]], *, temperature: float = 0.2) -> str:
        if self._i < len(self._plan):
            out = self._plan[self._i]
            self._i += 1
            return out
        return "Thought: 结束。\nFinal Answer: (stub 无更多步骤)"


def _demo_tools() -> Dict[str, ToolSpec]:
    def calc(expr: str) -> str:
        expr = expr.strip()
        if not re.fullmatch(r"[0-9+\-*/().\s]+", expr):
            return "错误：仅支持数字与 + - * / ( )"
        try:
            return str(eval(expr, {"__builtins__": {}}, {}))
        except Exception as exc:  # noqa: BLE001
            return f"计算错误: {exc}"

    return {
        "calculator": ToolSpec(
            name="calculator",
            description="对纯算术表达式求值，例如 2*(3+4)。",
            run=calc,
        ),
    }


def _demo() -> None:
    tools = _demo_tools()
    # 第一轮：调用计算器；第二轮：Final Answer
    stub = StubLLM(
        [
            "Thought: 需要先计算表达式。\n"
            "Action: calculator\n"
            "Action Input: (128 + 256) / 2",
            "Thought: 已有数值。\n"
            "Final Answer: 结果是 192。",
        ],
    )
    agent = SingleReactAgent(stub, tools, config=AgentConfig(max_steps=5))
    result = agent.run("帮我算 (128+256)/2，并只回答数值含义一句话。")
    print("[demo] Final:", result)


if __name__ == "__main__":
    _demo()
