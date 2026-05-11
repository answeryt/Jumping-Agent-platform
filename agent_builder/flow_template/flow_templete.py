"""
flow_templete.py

存放 create_flow.py 使用的 Flow 代码模板。
每个函数生成一种 Flow 类型的 Python 文件内容。
所有 Flow 继承 BaseFlow，复用 run_turn / MarkdownMemory。
"""

from __future__ import annotations

from typing import Dict, List, Optional


# ─────────────────────────────────────────────
# 辅助：生成 Flow 内联 Parser 类
# ─────────────────────────────────────────────

def _parser_class(flow_type: str, extra_fields: str = "") -> str:
    """生成 Flow 内联的 StepParser 类骨架。"""
    return f'''
class {flow_type.capitalize()}StepParser:
    """
    {flow_type} Flow 专用解析器。
    实现 StepParserProtocol，将 Agent 原始输出解析为 ParsedFlowStep。
    """

    def parse(self, agent_type: str, raw_text: str) -> ParsedFlowStep:
        state = self._extract_state(agent_type, raw_text)
        should_stop = self._extract_field(raw_text, "should_stop", "false").lower() == "true"
        next_agent = self._extract_field(raw_text, "next_agent", "none")
        next_task = self._extract_field(raw_text, "next_task", "none"){extra_fields}
        return ParsedFlowStep(
            state=state,
            next_agent=next_agent,
            next_task=next_task,
            should_stop=should_stop,
        )

    @staticmethod
    def _extract_field(text: str, field: str, default: str = "none") -> str:
        """从 Agent 输出中提取指定字段值。"""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith(f"{{field}}:"):
                value = stripped.split(":", 1)[1].strip()
                return value if value else default
        return default

    @staticmethod
    def _extract_state(agent_type: str, raw_text: str) -> AgentState:
        """从 Agent 输出中提取结构化状态。"""
        def _get(field: str) -> str:
            for line in raw_text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith(f"{{field}}:"):
                    val = stripped.split(":", 1)[1].strip()
                    return val if val else "none"
            return "none"

        return AgentState(
            context=AgentContext(
                goal=_get("goal"),
                user_request=_get("user_request"),
                known_info=_get("known_info"),
                phase=_get("phase"),
                constraints=_get("constraints"),
            ),
            output=AgentOutput(result=_get("result")),
            trace=AgentTrace(
                steps=_get("steps"),
                skills_used=_get("skills_used"),
            ),
            handoff=AgentHandoff(
                next_agent=_get("next_agent"),
                next_task=_get("next_task"),
                notes=_get("notes"),
            ),
        )
'''


# ─────────────────────────────────────────────
# 公共 import 头
# ─────────────────────────────────────────────

_COMMON_IMPORTS = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from Context.markdown_memroy import MarkdownMemory
from Context.markdown_schema import (
    AgentContext,
    AgentHandoff,
    AgentOutput,
    AgentState,
    AgentTrace,
)
from Model.base_model import ChatMessage
from Workflow.base_flow import (
    BaseFlow,
    FlowExecutionResult,
    FlowTurnResult,
    ParsedFlowStep,
)
'''

_ASYNC_IMPORTS = '''import asyncio
'''


# ─────────────────────────────────────────────
# 1. SequentialFlow（顺序链）
# ─────────────────────────────────────────────

def sequential_flow_py(agent_names: List[str]) -> str:
    """
    生成 SequentialFlow 骨架。
    A → B → C 固定顺序执行，不需要 LLM 决定路由。
    """
    agents_list = ", ".join(f'"{name}"' for name in agent_names)

    return f'''{_COMMON_IMPORTS}

{_parser_class("sequential")}


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

            # 将当前 agent 的结果作为下一个 agent 的输入
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


# ─────────────────────────────────────────────
# 2. RouterFlow（条件路由）
# ─────────────────────────────────────────────

def router_flow_py(dispatcher: str, branches: Dict[str, str]) -> str:
    """
    生成 RouterFlow 骨架。
    dispatcher agent 输出 route_key，根据条件映射表选择下一个 agent。
    """
    branches_dict = ", ".join(f'"{k}": "{v}"' for k, v in branches.items())

    return f'''{_COMMON_IMPORTS}

{_parser_class("router", """
        route_key = self._extract_field(raw_text, "route_key", "none")""")}


@dataclass(frozen=True)
class RouterFlowConfig:
    """RouterFlow 运行参数。"""
    dispatcher: str = "{dispatcher}"
    branches: dict = None
    max_turns: int = 10

    def __post_init__(self) -> None:
        if self.branches is None:
            object.__setattr__(self, "branches", {{{branches_dict}}})


class RouterFlow(BaseFlow):
    """
    条件路由 Flow：
    - dispatcher agent 分析任务并输出 route_key
    - 根据预定义的 branches 映射表选择目标 agent
    - 目标 agent 执行后返回结果
    """

    def __init__(self, *args: Any, config: Optional[RouterFlowConfig] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.config = config or RouterFlowConfig()

    def _resolve_route(self, raw_text: str) -> str:
        """从 dispatcher 输出中解析 route_key 并映射到目标 agent。"""
        parser = RouterStepParser()
        route_key = parser._extract_field(raw_text, "route_key", "").strip().lower()
        if not route_key or route_key == "none":
            raise RuntimeError(f"dispatcher 未输出有效的 route_key，原始输出: {{raw_text[:200]}}")
        if route_key not in self.config.branches:
            raise RuntimeError(
                f"route_key '{{route_key}}' 未在 branches 中注册，"
                f"可用: {{list(self.config.branches.keys())}}"
            )
        return self.config.branches[route_key]

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

        # Step 1: dispatcher 分析并路由
        dispatch_turn = self.run_turn(
            turn_index=1,
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

        # Step 2: 根据 route_key 选择目标 agent
        target_agent = self._resolve_route(dispatch_turn.raw_output)
        task_for_target = dispatch_turn.parsed.state.output.result
        if not task_for_target or task_for_target == "none":
            task_for_target = request_text

        history.append({{"role": "assistant", "content": dispatch_turn.raw_output}})

        # Step 3: 目标 agent 执行
        target_turn = self.run_turn(
            turn_index=2,
            agent_key=target_agent,
            task_text=task_for_target,
            history=history,
        )
        turns.append(target_turn)

        return FlowExecutionResult(
            stopped_by="route_complete",
            turns=turns,
            final_output=target_turn.raw_output,
            final_agent=target_agent,
        )
'''


# ─────────────────────────────────────────────
# 3. ParallelFlow（并行扇出-汇总）
# ─────────────────────────────────────────────

def parallel_flow_py(dispatcher: str, workers: List[str], aggregator: str) -> str:
    """
    生成 ParallelFlow 骨架。
    dispatcher 拆分任务 → workers 并行执行 → aggregator 汇总结果。
    """
    workers_list = ", ".join(f'"{w}"' for w in workers)

    return f'''{_COMMON_IMPORTS}{_ASYNC_IMPORTS}

{_parser_class("parallel")}


@dataclass(frozen=True)
class ParallelFlowConfig:
    """ParallelFlow 运行参数。"""
    dispatcher: str = "{dispatcher}"
    workers: tuple = ({workers_list},)
    aggregator: str = "{aggregator}"
    max_turns: int = {len(workers) + 4}


class ParallelFlow(BaseFlow):
    """
    并行扇出-汇总 Flow：
    - dispatcher agent 将任务拆分为子任务
    - 多个 worker agent 并行执行各自的子任务
    - aggregator agent 汇总所有 worker 的结果
    """

    def __init__(self, *args: Any, config: Optional[ParallelFlowConfig] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
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

        history: List[ChatMessage] = [{{"role": "user", "content": request_text}}]
        turns: List[FlowTurnResult] = []
        turn_counter = 0

        # Phase 1: dispatcher 拆分任务
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

        history.append({{"role": "assistant", "content": dispatch_turn.raw_output}})
        dispatch_result = dispatch_turn.parsed.state.output.result
        if not dispatch_result or dispatch_result == "none":
            dispatch_result = dispatch_turn.raw_output

        # Phase 2: workers 并行执行
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

        # 收集 worker 结果
        worker_results = []
        for wt in worker_turns:
            result = wt.parsed.state.output.result
            if not result or result == "none":
                result = wt.raw_output
            worker_results.append(f"[{{wt.agent_key}}]: {{result}}")
        aggregated_input = "\\n\\n".join(worker_results)

        # Phase 3: aggregator 汇总
        turn_counter += 1
        agg_history = list(history)
        for wt in worker_turns:
            agg_history.append({{"role": "assistant", "content": wt.raw_output}})

        agg_turn = self.run_turn(
            turn_index=turn_counter,
            agent_key=self.config.aggregator,
            task_text=aggregated_input,
            history=agg_history,
        )
        turns.append(agg_turn)

        return FlowExecutionResult(
            stopped_by="parallel_complete",
            turns=turns,
            final_output=agg_turn.raw_output,
            final_agent=self.config.aggregator,
        )
'''


# ─────────────────────────────────────────────
# 4. LoopFlow（循环/反思）
# ─────────────────────────────────────────────

def loop_flow_py(executor: str, evaluator: str, max_iterations: int = 5) -> str:
    """
    生成 LoopFlow 骨架。
    executor 执行 → evaluator 评估 → 不通过则反馈给 executor 重试。
    """

    return f'''{_COMMON_IMPORTS}

{_parser_class("loop", """
        verdict = self._extract_field(raw_text, "verdict", "fail")""")}


@dataclass(frozen=True)
class LoopFlowConfig:
    """LoopFlow 运行参数。"""
    executor: str = "{executor}"
    evaluator: str = "{evaluator}"
    max_iterations: int = {max_iterations}
    pass_verdicts: tuple = ("pass", "ok", "approved", "accept", "true")


class LoopFlow(BaseFlow):
    """
    循环反思 Flow：
    - executor agent 执行任务
    - evaluator agent 评估��果，输出 verdict（pass/fail）
    - fail 时将 evaluator 的反馈作为新 context 喂回 executor
    - 达到 max_iterations 或 verdict=pass 时终止
    """

    def __init__(self, *args: Any, config: Optional[LoopFlowConfig] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
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

        history: List[ChatMessage] = [{{"role": "user", "content": request_text}}]
        turns: List[FlowTurnResult] = []
        current_task = request_text
        turn_counter = 0

        for iteration in range(1, self.config.max_iterations + 1):
            # Step A: executor 执行
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
            history.append({{"role": "assistant", "content": exec_turn.raw_output}})

            # Step B: evaluator 评估
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
            history.append({{"role": "assistant", "content": eval_turn.raw_output}})

            # 检查 verdict
            parser = LoopStepParser()
            verdict = parser._extract_field(eval_turn.raw_output, "verdict", "fail")

            if self._is_pass(verdict):
                return FlowExecutionResult(
                    stopped_by="evaluation_passed",
                    turns=turns,
                    final_output=exec_turn.raw_output,
                    final_agent=self.config.executor,
                )

            # 未通过：将 evaluator 反馈作为下一轮 executor 的输入
            feedback = eval_turn.parsed.state.output.result
            if not feedback or feedback == "none":
                feedback = eval_turn.raw_output
            current_task = (
                f"根据以下反馈修改你的输出：\\n\\n"
                f"原始任务: {{request_text}}\\n\\n"
                f"评估反馈: {{feedback}}"
            )

        # 达到最大迭代次数
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


# ─────────────────────────────────────────────
# 5. DebateFlow（多方讨论）
# ─────────────────────────────────────────────

def debate_flow_py(participants: List[str], moderator: str, max_rounds: int = 5) -> str:
    """
    生成 DebateFlow 骨架。
    多个 participant agent 轮流发言，moderator 判断是否达成共识。
    """
    participants_list = ", ".join(f'"{p}"' for p in participants)

    return f'''{_COMMON_IMPORTS}

{_parser_class("debate", """
        consensus = self._extract_field(raw_text, "consensus", "false")""")}


@dataclass(frozen=True)
class DebateFlowConfig:
    """DebateFlow 运行参数。"""
    participants: tuple = ({participants_list},)
    moderator: str = "{moderator}"
    max_rounds: int = {max_rounds}
    consensus_values: tuple = ("true", "yes", "consensus", "agreed", "resolved")


class DebateFlow(BaseFlow):
    """
    多方讨论 Flow：
    - 多个 participant agent 共享同一对话历史，轮流发言
    - 每轮结束后 moderator agent 判断是否达成共识
    - consensus=true 或达到 max_rounds 时终止
    """

    def __init__(self, *args: Any, config: Optional[DebateFlowConfig] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
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

        # 共享对话历史：所有 participant 和 moderator 看到同一份
        shared_history: List[ChatMessage] = [{{"role": "user", "content": request_text}}]
        turns: List[FlowTurnResult] = []
        turn_counter = 0

        for round_num in range(1, self.config.max_rounds + 1):
            round_context = (
                f"第 {{round_num}}/{{self.config.max_rounds}} 轮讨论。\\n"
                f"议题: {{request_text}}"
            )

            # 每个 participant 轮流发言
            for participant in self.config.participants:
                turn_counter += 1
                p_turn = self.run_turn(
                    turn_index=turn_counter,
                    agent_key=participant,
                    task_text=round_context,
                    history=shared_history,
                )
                turns.append(p_turn)
                shared_history.append({{
                    "role": "assistant",
                    "content": f"[{{participant}}]: {{p_turn.raw_output}}",
                }})

                if p_turn.parsed.should_stop:
                    return FlowExecutionResult(
                        stopped_by="parser_stop_signal",
                        turns=turns,
                        final_output=p_turn.raw_output,
                        final_agent=participant,
                    )

            # moderator 评估本轮讨论
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
            shared_history.append({{
                "role": "assistant",
                "content": f"[{{self.config.moderator}}]: {{mod_turn.raw_output}}",
            }})

            # 检查共识
            parser = DebateStepParser()
            consensus = parser._extract_field(mod_turn.raw_output, "consensus", "false")

            if self._is_consensus(consensus):
                return FlowExecutionResult(
                    stopped_by="consensus_reached",
                    turns=turns,
                    final_output=mod_turn.raw_output,
                    final_agent=self.config.moderator,
                )

        # 达到最大轮次
        return FlowExecutionResult(
            stopped_by="max_rounds_reached",
            turns=turns,
            final_output=turns[-1].raw_output,
            final_agent=self.config.moderator,
        )
'''


# ─────────────────────────────────────────────
# 6. HierarchicalFlow（层级委派）
# ─────────────────────────────────────────────

def hierarchical_flow_py(manager: str, workers: List[str], max_delegation_rounds: int = 3) -> str:
    """
    生成 HierarchicalFlow 骨架。
    manager 分解任务并委派给 workers，workers 完成后汇报，manager 决定是否继续。
    """
    workers_list = ", ".join(f'"{w}"' for w in workers)

    return f'''{_COMMON_IMPORTS}

{_parser_class("hierarchical", """
        delegation_complete = self._extract_field(raw_text, "delegation_complete", "false")""")}


@dataclass(frozen=True)
class HierarchicalFlowConfig:
    """HierarchicalFlow 运行参数。"""
    manager: str = "{manager}"
    workers: tuple = ({workers_list},)
    max_delegation_rounds: int = {max_delegation_rounds}
    complete_values: tuple = ("true", "yes", "done", "complete", "finished")


class HierarchicalFlow(BaseFlow):
    """
    层级委派 Flow：
    - manager agent 分解任务，指定 assigned_to 和 subtask
    - worker agent 执行被分配的子任务并汇报
    - manager 审查所有 worker 结果，决定是否继续委派或结束
    """

    def __init__(self, *args: Any, config: Optional[HierarchicalFlowConfig] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
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

        # 如果解析不到结构化分配，回退：把整个输出分配给第一个 worker
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

        history: List[ChatMessage] = [{{"role": "user", "content": request_text}}]
        turns: List[FlowTurnResult] = []
        turn_counter = 0

        for round_num in range(1, self.config.max_delegation_rounds + 1):
            # Phase A: manager 分解/分配任务
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
            history.append({{"role": "assistant", "content": mgr_turn.raw_output}})

            if mgr_turn.parsed.should_stop:
                return FlowExecutionResult(
                    stopped_by="parser_stop_signal",
                    turns=turns,
                    final_output=mgr_turn.raw_output,
                    final_agent=self.config.manager,
                )

            # 检查 manager 是否认为任务已完成
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

            # Phase B: 解析分配并调度 workers
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
                history.append({{
                    "role": "assistant",
                    "content": f"[{{worker_key}}]: {{worker_turn.raw_output}}",
                }})

        # 达到最大委派轮次，让 manager 做最终总结
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

        return FlowExecutionResult(
            stopped_by="max_delegation_rounds_reached",
            turns=turns,
            final_output=final_turn.raw_output,
            final_agent=self.config.manager,
        )
'''


# ─────────────────────────────────────────────
# 7. SupervisorFlow（监督编排）
# ─────────────────────────────────────────────

def supervisor_flow_py(supervisor: str, agents: List[str], max_rounds: int = 5) -> str:
    """
    生成 SupervisorFlow 骨架。
    supervisor 观察全局状态，按轮次选择一个 agent 执行，直到完成或达到上限。
    """
    agents_list = ", ".join(f'"{a}"' for a in agents)

    return f'''{_COMMON_IMPORTS}

{_parser_class("supervisor", """
        assigned_to = self._extract_field(raw_text, "assigned_to", "none")""")}


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
