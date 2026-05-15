"""
debate_template.py

DebateFlow 模板生成函数。
"""

from __future__ import annotations

from typing import List

from flow_template.common import COMMON_IMPORTS, parser_class



def debate_flow_py(participants: List[str], moderator: str, max_rounds: int = 5) -> str:
    """
    生成 DebateFlow 骨架。
    多个 participant agent 轮流发言，moderator 判断是否达成共识。
    """
    participants_list = ", ".join(f'"{p}"' for p in participants)

    return f'''{COMMON_IMPORTS}

{parser_class("debate", """
        consensus = self._extract_field(raw_text, \"consensus\", \"false\")""")}


@dataclass(frozen=True)
class DebateFlowConfig:
    """DebateFlow 运行参数。"""
    participants: tuple = ({participants_list},)
    moderator: str = "{moderator}"
    max_rounds: int = {max_rounds}
    consensus_values: tuple = ("true", "yes", "consensus", "agreed", "resolved")


class DebateFlow(FlowMemoryMixin, BaseFlow):
    """
    多方讨论 Flow：
    - 多个 participant agent 共享同一对话历史，轮流发言
    - 每轮结束后 moderator agent 判断是否达成共识
    - consensus=true 或达到 max_rounds 时终止
    """

    def __init__(self, *args: Any, config: Optional[DebateFlowConfig] = None, **kwargs: Any) -> None:
        memory = kwargs.pop("memory", None)
        user_id = kwargs.pop("user_id", "default_user")
        session_id = kwargs.pop("session_id", "default_session")
        super().__init__(*args, **kwargs)
        self._init_working_memory(memory=memory, user_id=user_id, session_id=session_id)
        self.config = config or DebateFlowConfig()

    def _is_consensus(self, value: str) -> bool:
        return value.strip().lower() in self.config.consensus_values

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

        shared_history = self._start_history(
            request_text,
            user_id=kwargs.pop("user_id", None),
            session_id=kwargs.pop("session_id", None),
        )
        turns: List[FlowTurnResult] = []
        turn_counter = 0

        for round_num in range(1, self.config.max_rounds + 1):
            round_context = (
                f"第 {{round_num}}/{{self.config.max_rounds}} 轮讨论。\\n"
                f"议题: {{request_text}}"
            )

            for participant in self.config.participants:
                turn_counter += 1
                p_turn = self.run_turn(
                    turn_index=turn_counter,
                    agent_key=participant,
                    task_text=round_context,
                    history=shared_history,
                )
                turns.append(p_turn)
                shared_history = self._append_history(
                    "assistant",
                    f"[{{participant}}]: {{p_turn.raw_output}}",
                    agent_key=participant,
                    turn_index=turn_counter,
                )

                if p_turn.parsed.should_stop:
                    return FlowExecutionResult(
                        stopped_by="parser_stop_signal",
                        turns=turns,
                        final_output=p_turn.raw_output,
                        final_agent=participant,
                    )

            turn_counter += 1
            mod_context = (
                f"请判断讨论是否达成共识。\\n"
                f"当前轮次: {{round_num}}/{{self.config.max_rounds}}\\n"
                f"议题: {{request_text}}"
            )
            mod_turn = self.run_turn(
                turn_index=turn_counter,
                agent_key=self.config.moderator,
                task_text=mod_context,
                history=shared_history,
            )
            turns.append(mod_turn)
            shared_history = self._append_history(
                "assistant",
                f"[{{self.config.moderator}}]: {{mod_turn.raw_output}}",
                agent_key=self.config.moderator,
                turn_index=turn_counter,
            )

            parser = DebateStepParser()
            consensus = parser._extract_field(mod_turn.raw_output, "consensus", "false")

            if self._is_consensus(consensus):
                return FlowExecutionResult(
                    stopped_by="consensus_reached",
                    turns=turns,
                    final_output=mod_turn.raw_output,
                    final_agent=self.config.moderator,
                )

        return FlowExecutionResult(
            stopped_by="max_rounds_reached",
            turns=turns,
            final_output=turns[-1].raw_output,
            final_agent=self.config.moderator,
        )
'''
