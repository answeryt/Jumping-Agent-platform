"""
supervisor_template.py

SupervisorFlow 模板生成函数。
"""

from __future__ import annotations

from typing import List

from flow_template.common import COMMON_IMPORTS, parser_class



def supervisor_flow_py(supervisor: str, agents: List[str], max_rounds: int = 5) -> str:
    """
    生成 SupervisorFlow 骨架。
    supervisor 观察全局状态，按轮次选择一个 agent 执行，直到完成或达到上限。
    """
    agents_list = ", ".join(f'"{a}"' for a in agents)

    return f'''{COMMON_IMPORTS}

{parser_class("supervisor", """
        assigned_to = self._extract_field(raw_text, \"assigned_to\", \"none\")""")}


@dataclass(frozen=True)
class SupervisorFlowConfig:
    """SupervisorFlow 运行参数。"""
    supervisor: str = "{supervisor}"
    agents: tuple = ({agents_list},)
    max_rounds: int = {max_rounds}


class SupervisorFlow(BaseFlow):
    """
    监督编排 Flow：
    - supervisor agent 观察全局进度并决定下一步交给哪个 agent
    - 被调度 agent 执行后把结果写回共享历史
    - supervisor 输出 should_stop=true 或达到 max_rounds 时终止
    """

    def __init__(self, *args: Any, config: Optional[SupervisorFlowConfig] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.config = config or SupervisorFlowConfig()

    def _resolve_agent(self, raw_text: str) -> str:
        parser = SupervisorStepParser()
        assigned_to = parser._extract_field(raw_text, "assigned_to", "").strip().lower()
        if assigned_to in self.config.agents:
            return assigned_to
        if self.config.agents:
            return self.config.agents[0]
        raise RuntimeError("SupervisorFlow 至少需要 1 个可调度 agent")

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
        current_context = request_text
        turn_counter = 0

        for round_num in range(1, self.config.max_rounds + 1):
            turn_counter += 1
            supervisor_context = (
                f"请基于当前上下文决定下一步调度哪个 agent。\\n"
                f"轮次: {{round_num}}/{{self.config.max_rounds}}\\n"
                f"可选 agents: {{', '.join(self.config.agents)}}\\n\\n"
                f"上下文:\\n{{current_context}}"
            )
            supervisor_turn = self.run_turn(
                turn_index=turn_counter,
                agent_key=self.config.supervisor,
                task_text=supervisor_context,
                history=history,
            )
            turns.append(supervisor_turn)
            history.append({{"role": "assistant", "content": supervisor_turn.raw_output}})

            if supervisor_turn.parsed.should_stop:
                return FlowExecutionResult(
                    stopped_by="supervisor_stop_signal",
                    turns=turns,
                    final_output=supervisor_turn.raw_output,
                    final_agent=self.config.supervisor,
                )

            target_agent = self._resolve_agent(supervisor_turn.raw_output)
            target_task = supervisor_turn.parsed.next_task
            if not target_task or target_task == "none":
                target_task = supervisor_turn.parsed.state.output.result
            if not target_task or target_task == "none":
                target_task = request_text

            turn_counter += 1
            agent_turn = self.run_turn(
                turn_index=turn_counter,
                agent_key=target_agent,
                task_text=target_task,
                history=history,
            )
            turns.append(agent_turn)
            history.append({{
                "role": "assistant",
                "content": f"[{{target_agent}}]: {{agent_turn.raw_output}}",
            }})

            agent_result = agent_turn.parsed.state.output.result
            if not agent_result or agent_result == "none":
                agent_result = agent_turn.raw_output
            current_context = (
                f"原始任务: {{request_text}}\\n\\n"
                f"最近执行 agent: {{target_agent}}\\n"
                f"最近结果:\\n{{agent_result}}"
            )

        return FlowExecutionResult(
            stopped_by="max_rounds_reached",
            turns=turns,
            final_output=turns[-1].raw_output,
            final_agent=turns[-1].agent_key,
        )
'''
