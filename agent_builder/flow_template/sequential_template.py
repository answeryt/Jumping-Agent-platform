"""
sequential_template.py

SequentialFlow 模板生成函数。
"""

from __future__ import annotations

from typing import List

from flow_template.common import COMMON_IMPORTS, parser_class



def sequential_flow_py(agent_names: List[str]) -> str:
    """
    生成 SequentialFlow 骨架。
    A → B → C 固定顺序执行，不需要 LLM 决定路由。
    """
    agents_list = ", ".join(f'"{name}"' for name in agent_names)

    return f'''{COMMON_IMPORTS}

{parser_class("sequential")}


@dataclass(frozen=True)
class SequentialFlowConfig:
    """SequentialFlow 运行参数。"""
    agent_order: tuple = ({agents_list},)
    max_turns: int = {len(agent_names) + 2}


class SequentialFlow(BaseFlow):
    """
    顺序链 Flow：
    - agent 按固定顺序依次执行
    - 每个 agent 的输出作为下一个的输入
    - 不依赖 LLM 决定路由
    """

    def __init__(self, *args: Any, config: Optional[SequentialFlowConfig] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.config = config or SequentialFlowConfig()

    def execute(
        self,
        user_request: str,
        *,
        max_turns: Optional[int] = None,
        **kwargs: Any,
    ) -> FlowExecutionResult:
        request_text = (user_request or "").strip()
        if not request_text:
            raise ValueError("user_request 不能为空")

        history: List[ChatMessage] = [{{"role": "user", "content": request_text}}]
        turns: List[FlowTurnResult] = []
        current_task = request_text

        for idx, agent_key in enumerate(self.config.agent_order, start=1):
            if agent_key not in [a for a in self.list_agents()]:
                raise RuntimeError(f"未注册 agent: {{agent_key}}")

            turn = self.run_turn(
                turn_index=idx,
                agent_key=agent_key,
                task_text=current_task,
                history=history,
            )
            turns.append(turn)

            if turn.parsed.should_stop:
                return FlowExecutionResult(
                    stopped_by="parser_stop_signal",
                    turns=turns,
                    final_output=turn.raw_output,
                    final_agent=agent_key,
                )

            current_task = turn.parsed.state.output.result
            if not current_task or current_task == "none":
                current_task = turn.raw_output
            history.append({{"role": "assistant", "content": turn.raw_output}})

        last_turn = turns[-1]
        return FlowExecutionResult(
            stopped_by="sequence_complete",
            turns=turns,
            final_output=last_turn.raw_output,
            final_agent=self.config.agent_order[-1],
        )
'''
