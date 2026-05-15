"""
hierarchical_template.py

HierarchicalFlow 模板生成函数。
"""

from __future__ import annotations

from typing import List

from flow_template.common import COMMON_IMPORTS, parser_class



def hierarchical_flow_py(manager: str, workers: List[str], max_delegation_rounds: int = 3) -> str:
    """
    生成 HierarchicalFlow 骨架。
    manager 分解任务并委派给 workers，workers 完成后汇报，manager 决定是否继续。
    """
    workers_list = ", ".join(f'"{w}"' for w in workers)

    return f'''{COMMON_IMPORTS}

{parser_class("hierarchical", """
        delegation_complete = self._extract_field(raw_text, \"delegation_complete\", \"false\")""")}


@dataclass(frozen=True)
class HierarchicalFlowConfig:
    """HierarchicalFlow 运行参数。"""
    manager: str = "{manager}"
    workers: tuple = ({workers_list},)
    max_delegation_rounds: int = {max_delegation_rounds}
    complete_values: tuple = ("true", "yes", "done", "complete", "finished")


class HierarchicalFlow(FlowMemoryMixin, BaseFlow):
    """
    层级委派 Flow：
    - manager agent 分解任务，指定 assigned_to 和 subtask
    - worker agent 执行被分配的子任务并汇报
    - manager 审查所有 worker 结果，决定是否继续委派或结束
    """

    def __init__(self, *args: Any, config: Optional[HierarchicalFlowConfig] = None, **kwargs: Any) -> None:
        memory = kwargs.pop("memory", None)
        user_id = kwargs.pop("user_id", "default_user")
        session_id = kwargs.pop("session_id", "default_session")
        super().__init__(*args, **kwargs)
        self._init_working_memory(memory=memory, user_id=user_id, session_id=session_id)
        self.config = config or HierarchicalFlowConfig()

    def _is_complete(self, value: str) -> bool:
        return value.strip().lower() in self.config.complete_values

    def _parse_assignments(self, raw_text: str) -> List[Dict[str, str]]:
        """
        从 manager 输出中解析子任务分配。
        期望格式（每行一条）：
            assigned_to: <worker_name>, subtask: <任务描述>
        """
        assignments: List[Dict[str, str]] = []
        for line in raw_text.splitlines():
            stripped = line.strip()
            if "assigned_to:" in stripped.lower() and "subtask:" in stripped.lower():
                parts = stripped.split(",", 1)
                assigned = ""
                subtask = ""
                for part in parts:
                    p = part.strip()
                    if p.lower().startswith("assigned_to:"):
                        assigned = p.split(":", 1)[1].strip()
                    elif p.lower().startswith("subtask:"):
                        subtask = p.split(":", 1)[1].strip()
                if assigned and subtask:
                    assignments.append({{"assigned_to": assigned, "subtask": subtask}})

        if not assignments and self.config.workers:
            assignments.append({{
                "assigned_to": self.config.workers[0],
                "subtask": raw_text.strip(),
            }})
        return assignments

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
        )
        turns: List[FlowTurnResult] = []
        turn_counter = 0

        for round_num in range(1, self.config.max_delegation_rounds + 1):
            turn_counter += 1
            manager_context = request_text if round_num == 1 else (
                f"请根据以下 worker 汇报决定下一步：\\n\\n"
                + "\\n".join(
                    f"[{{t.agent_key}}]: {{t.raw_output}}"
                    for t in turns
                    if t.agent_key != self.config.manager
                )
            )
            mgr_turn = self.run_turn(
                turn_index=turn_counter,
                agent_key=self.config.manager,
                task_text=manager_context,
                history=history,
            )
            turns.append(mgr_turn)
            history = self._append_history(
                "assistant",
                mgr_turn.raw_output,
                agent_key=self.config.manager,
                turn_index=turn_counter,
            )

            if mgr_turn.parsed.should_stop:
                return FlowExecutionResult(
                    stopped_by="parser_stop_signal",
                    turns=turns,
                    final_output=mgr_turn.raw_output,
                    final_agent=self.config.manager,
                )

            parser = HierarchicalStepParser()
            delegation_complete = parser._extract_field(
                mgr_turn.raw_output, "delegation_complete", "false"
            )
            if self._is_complete(delegation_complete):
                return FlowExecutionResult(
                    stopped_by="delegation_complete",
                    turns=turns,
                    final_output=mgr_turn.raw_output,
                    final_agent=self.config.manager,
                )

            assignments = self._parse_assignments(mgr_turn.raw_output)
            for assignment in assignments:
                worker_key = assignment["assigned_to"].strip().lower()
                if worker_key not in self.config.workers:
                    continue
                turn_counter += 1
                worker_turn = self.run_turn(
                    turn_index=turn_counter,
                    agent_key=worker_key,
                    task_text=assignment["subtask"],
                    history=history,
                )
                turns.append(worker_turn)
                history = self._append_history(
                    "assistant",
                    f"[{{worker_key}}]: {{worker_turn.raw_output}}",
                    agent_key=worker_key,
                    turn_index=turn_counter,
                )

        turn_counter += 1
        final_context = (
            f"已达到最大委派轮次 ({{self.config.max_delegation_rounds}})。\\n"
            f"请总结所有 worker 的成果并给出最终结论。"
        )
        final_turn = self.run_turn(
            turn_index=turn_counter,
            agent_key=self.config.manager,
            task_text=final_context,
            history=history,
        )
        turns.append(final_turn)
        self._append_history(
            "assistant",
            final_turn.raw_output,
            agent_key=self.config.manager,
            turn_index=turn_counter,
        )

        return FlowExecutionResult(
            stopped_by="max_delegation_rounds_reached",
            turns=turns,
            final_output=final_turn.raw_output,
            final_agent=self.config.manager,
        )
'''
