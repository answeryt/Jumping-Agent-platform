"""
parallel_template.py

ParallelFlow 模板生成函数。
"""

from __future__ import annotations

from typing import List

from flow_template.common import ASYNC_IMPORTS, COMMON_IMPORTS, parser_class



def parallel_flow_py(dispatcher: str, workers: List[str], aggregator: str) -> str:
    """
    生成 ParallelFlow 骨架。
    dispatcher 拆分任务 → workers 并行执行 → aggregator 汇总结果。
    """
    workers_list = ", ".join(f'"{w}"' for w in workers)

    return f'''{COMMON_IMPORTS}{ASYNC_IMPORTS}

{parser_class("parallel")}


@dataclass(frozen=True)
class ParallelFlowConfig:
    """ParallelFlow 运行参数。"""
    dispatcher: str = "{dispatcher}"
    workers: tuple = ({workers_list},)
    aggregator: str = "{aggregator}"
    max_turns: int = {len(workers) + 4}


class ParallelFlow(FlowMemoryMixin, BaseFlow):
    """
    并行扇出-汇总 Flow：
    - dispatcher agent 将任务拆分为子任务
    - 多个 worker agent 并行执行各自的子任务
    - aggregator agent 汇总所有 worker 的结果
    """

    def __init__(self, *args: Any, config: Optional[ParallelFlowConfig] = None, **kwargs: Any) -> None:
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
        self.config = config or ParallelFlowConfig()

    def _run_worker(
        self,
        turn_index: int,
        agent_key: str,
        task_text: str,
        base_history: List[ChatMessage],
    ) -> FlowTurnResult:
        """单个 worker 的执行（供并行调用）。"""
        worker_history = list(base_history)
        return self.run_turn(
            turn_index=turn_index,
            agent_key=agent_key,
            task_text=task_text,
            history=worker_history,
        )

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
        turn_counter = 0

        turn_counter += 1
        dispatch_turn = self.run_turn(
            turn_index=turn_counter,
            agent_key=self.config.dispatcher,
            task_text=request_text,
            history=history,
        )
        turns.append(dispatch_turn)

        if dispatch_turn.parsed.should_stop:
            return FlowExecutionResult(
                stopped_by="parser_stop_signal",
                turns=turns,
                final_output=dispatch_turn.raw_output,
                final_agent=self.config.dispatcher,
            )

        history = self._append_history(
            "assistant",
            dispatch_turn.raw_output,
            agent_key=self.config.dispatcher,
            turn_index=turn_counter,
        )
        dispatch_result = dispatch_turn.parsed.state.output.result
        if not dispatch_result or dispatch_result == "none":
            dispatch_result = dispatch_turn.raw_output

        worker_turns: List[FlowTurnResult] = []
        for worker_key in self.config.workers:
            turn_counter += 1
            wt = self._run_worker(
                turn_index=turn_counter,
                agent_key=worker_key,
                task_text=dispatch_result,
                base_history=history,
            )
            worker_turns.append(wt)
        turns.extend(worker_turns)

        worker_results = []
        for wt in worker_turns:
            result = wt.parsed.state.output.result
            if not result or result == "none":
                result = wt.raw_output
            worker_results.append(f"[{{wt.agent_key}}]: {{result}}")
            history = self._append_history(
                "assistant",
                f"[{{wt.agent_key}}]: {{wt.raw_output}}",
                agent_key=wt.agent_key,
                turn_index=wt.turn_index,
            )
        aggregated_input = "\\n\\n".join(worker_results)

        turn_counter += 1
        agg_history = self._history()

        agg_turn = self.run_turn(
            turn_index=turn_counter,
            agent_key=self.config.aggregator,
            task_text=aggregated_input,
            history=agg_history,
        )
        turns.append(agg_turn)
        self._append_history(
            "assistant",
            agg_turn.raw_output,
            agent_key=self.config.aggregator,
            turn_index=turn_counter,
        )

        return FlowExecutionResult(
            stopped_by="parallel_complete",
            turns=turns,
            final_output=agg_turn.raw_output,
            final_agent=self.config.aggregator,
        )
'''
