"""
loop_template.py

LoopFlow 模板生成函数。
"""

from __future__ import annotations

from flow_template.common import COMMON_IMPORTS, parser_class



def loop_flow_py(executor: str, evaluator: str, max_iterations: int = 5) -> str:
    """
    生成 LoopFlow 骨架。
    executor 执行 → evaluator 评估 → 不通过则反馈给 executor 重试。
    """

    return f'''{COMMON_IMPORTS}

{parser_class("loop", """
        verdict = self._extract_field(raw_text, \"verdict\", \"fail\")""")}


@dataclass(frozen=True)
class LoopFlowConfig:
    """LoopFlow 运行参数。"""
    executor: str = "{executor}"
    evaluator: str = "{evaluator}"
    max_iterations: int = {max_iterations}
    pass_verdicts: tuple = ("pass", "ok", "approved", "accept", "true")


class LoopFlow(FlowMemoryMixin, BaseFlow):
    """
    循环反思 Flow：
    - executor agent 执行任务
    - evaluator agent 评估结果，输出 verdict（pass/fail）
    - fail 时将 evaluator 的反馈作为新 context 喂回 executor
    - 达到 max_iterations 或 verdict=pass 时终止
    """

    def __init__(self, *args: Any, config: Optional[LoopFlowConfig] = None, **kwargs: Any) -> None:
        memory = kwargs.pop("memory", None)
        user_id = kwargs.pop("user_id", None)
        session_id = kwargs.pop("session_id", None)
        md_path = kwargs.pop("md_path", None)
        big_session_id = kwargs.pop("big_session_id", None)
        small_session_id = kwargs.pop("small_session_id", None)
        super().__init__(*args, **kwargs)
        self._init_working_memory(
            memory=memory,
            user_id=user_id,
            session_id=session_id,
            md_path=md_path,
            big_session_id=big_session_id,
            small_session_id=small_session_id,
        )
        self.config = config or LoopFlowConfig()

    def _is_pass(self, verdict: str) -> bool:
        return verdict.strip().lower() in self.config.pass_verdicts

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

        history = self._start_history(
            request_text,
            user_id=kwargs.pop("user_id", None),
            session_id=kwargs.pop("session_id", None),
            md_path=kwargs.pop("md_path", None),
            big_session_id=kwargs.pop("big_session_id", None),
            small_session_id=kwargs.pop("small_session_id", None),
        )
        turns: List[FlowTurnResult] = []
        current_task = request_text
        turn_counter = 0

        for iteration in range(1, self.config.max_iterations + 1):
            turn_counter += 1
            exec_turn = self.run_turn(
                turn_index=turn_counter,
                agent_key=self.config.executor,
                task_text=current_task,
                history=history,
            )
            turns.append(exec_turn)

            if exec_turn.parsed.should_stop:
                return FlowExecutionResult(
                    stopped_by="parser_stop_signal",
                    turns=turns,
                    final_output=exec_turn.raw_output,
                    final_agent=self.config.executor,
                )

            exec_result = exec_turn.parsed.state.output.result
            if not exec_result or exec_result == "none":
                exec_result = exec_turn.raw_output
            history = self._append_history(
                "assistant",
                exec_turn.raw_output,
                agent_key=self.config.executor,
                turn_index=turn_counter,
            )

            turn_counter += 1
            eval_context = (
                f"请评估以下输出的质量：\\n\\n"
                f"原始任务: {{request_text}}\\n\\n"
                f"当前迭代: {{iteration}}/{{self.config.max_iterations}}\\n\\n"
                f"executor 输出:\\n{{exec_result}}"
            )
            eval_turn = self.run_turn(
                turn_index=turn_counter,
                agent_key=self.config.evaluator,
                task_text=eval_context,
                history=history,
            )
            turns.append(eval_turn)
            history = self._append_history(
                "assistant",
                eval_turn.raw_output,
                agent_key=self.config.evaluator,
                turn_index=turn_counter,
            )

            parser = LoopStepParser()
            verdict = parser._extract_field(eval_turn.raw_output, "verdict", "fail")

            if self._is_pass(verdict):
                return FlowExecutionResult(
                    stopped_by="evaluation_passed",
                    turns=turns,
                    final_output=exec_turn.raw_output,
                    final_agent=self.config.executor,
                )

            feedback = eval_turn.parsed.state.output.result
            if not feedback or feedback == "none":
                feedback = eval_turn.raw_output
            current_task = (
                f"根据以下反馈修改你的输出：\\n\\n"
                f"原始任务: {{request_text}}\\n\\n"
                f"评估反馈: {{feedback}}"
            )

        last_exec_turn = next(
            (t for t in reversed(turns) if t.agent_key == self.config.executor),
            turns[-1],
        )
        return FlowExecutionResult(
            stopped_by="max_iterations_reached",
            turns=turns,
            final_output=last_exec_turn.raw_output,
            final_agent=self.config.executor,
        )
'''
