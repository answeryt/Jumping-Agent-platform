"""
router_template.py

RouterFlow 模板生成函数。
"""

from __future__ import annotations

from typing import Dict

from flow_template.common import COMMON_IMPORTS, parser_class



def router_flow_py(dispatcher: str, branches: Dict[str, str]) -> str:
    """
    生成 RouterFlow 骨架。
    dispatcher agent 输出 route_key，根据条件映射表选择下一个 agent。
    """
    branches_dict = ", ".join(f'"{k}": "{v}"' for k, v in branches.items())

    return f'''{COMMON_IMPORTS}

{parser_class("router", """
        route_key = self._extract_field(raw_text, \"route_key\", \"none\")""")}


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

        target_agent = self._resolve_route(dispatch_turn.raw_output)
        task_for_target = dispatch_turn.parsed.state.output.result
        if not task_for_target or task_for_target == "none":
            task_for_target = request_text

        history.append({{"role": "assistant", "content": dispatch_turn.raw_output}})

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
