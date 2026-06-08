from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from Model.base_model import ChatMessage
from Workflow.base_flow import (
    AgentContext,
    AgentHandoff,
    AgentOutput,
    AgentState,
    AgentTrace,
    BaseFlow,
    FlowExecutionResult,
    FlowTurnResult,
    ParsedFlowStep,
)

for _parent in Path(__file__).resolve().parents:
    if (_parent / "backend" / "memory" / "working_memory").exists():
        sys.path.insert(0, str(_parent))
        break

from backend.memory.working_memory import AgentWorkingMemory


class FlowMemoryMixin:
    """Shared short-term memory helpers for generated flows.

    Generated flows must be bound to a concrete user + big/small session at
    construction time. There are no ``default_user`` / ``default_session``
    fallbacks - chat traffic without those ids would silently leak between
    conversations and is therefore rejected up front.
    """

    def _init_working_memory(
        self,
        *,
        memory: Optional[AgentWorkingMemory] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        md_path: Optional[Any] = None,
        big_session_id: Optional[str] = None,
        small_session_id: Optional[str] = None,
    ) -> None:
        if memory is not None:
            self.memory = memory
            return
        if not user_id:
            raise ValueError("FlowMemoryMixin requires user_id; no default is allowed")
        if big_session_id and small_session_id:
            self.memory = AgentWorkingMemory.for_md_session(
                user_id=user_id,
                big_session_id=big_session_id,
                small_session_id=small_session_id,
            )
            return
        if not session_id:
            raise ValueError(
                "FlowMemoryMixin requires session_id when big/small session ids are missing"
            )
        self.memory = AgentWorkingMemory(
            user_id=user_id,
            session_id=session_id,
            md_path=md_path,
            big_session_id=big_session_id,
            small_session_id=small_session_id,
        )

    def _start_history(
        self,
        request_text: str,
        *,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        md_path: Optional[Any] = None,
        big_session_id: Optional[str] = None,
        small_session_id: Optional[str] = None,
    ) -> List[ChatMessage]:
        if user_id or session_id or md_path or big_session_id or small_session_id:
            self.memory = self.memory.for_session(
                user_id=user_id,
                session_id=session_id,
                md_path=md_path,
                big_session_id=big_session_id,
                small_session_id=small_session_id,
            )
        self.memory.append("user", request_text, agent_key="shared")
        return self.memory.get_history()

    def _append_history(
        self,
        role: str,
        content: str,
        *,
        agent_key: str = "shared",
        turn_index: Optional[int] = None,
    ) -> List[ChatMessage]:
        self.memory.append(
            role,
            content,
            agent_key=agent_key,
            turn_index=turn_index,
        )
        return self.memory.get_history()

    def _history(self) -> List[ChatMessage]:
        return self.memory.get_history()



class SequentialStepParser:
    """
    sequential Flow 专用解析器。
    实现 StepParserProtocol，将 Agent 原始输出解析为 ParsedFlowStep。
    """

    def parse(self, agent_type: str, raw_text: str) -> ParsedFlowStep:
        state = self._extract_state(agent_type, raw_text)
        should_stop = self._extract_field(raw_text, "should_stop", "false").lower() == "true"
        next_agent = self._extract_field(raw_text, "next_agent", "none")
        next_task = self._extract_field(raw_text, "next_task", "none")
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
            if stripped.lower().startswith(f"{field}:"):
                value = stripped.split(":", 1)[1].strip()
                return value if value else default
        return default

    @staticmethod
    def _extract_state(agent_type: str, raw_text: str) -> AgentState:
        """从 Agent 输出中提取结构化状态。"""
        def _get(field: str) -> str:
            for line in raw_text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith(f"{field}:"):
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



@dataclass(frozen=True)
class SequentialFlowConfig:
    """SequentialFlow 运行参数。"""
    agent_order: tuple = ("routing", "tech_branch", "business_branch", "risk_branch", "merge_results",)
    max_turns: int = 7


class SequentialFlow(FlowMemoryMixin, BaseFlow):
    """
    顺序链 Flow：
    - agent 按固定顺序依次执行
    - 每个 agent 的输出作为下一个的输入
    - 不依赖 LLM 决定路由
    """

    def __init__(self, *args: Any, config: Optional[SequentialFlowConfig] = None, **kwargs: Any) -> None:
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

        for idx, agent_key in enumerate(self.config.agent_order, start=1):
            if agent_key not in [a for a in self.list_agents()]:
                raise RuntimeError(f"未注册 agent: {agent_key}")

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
            history = self._append_history(
                "assistant",
                turn.raw_output,
                agent_key=agent_key,
                turn_index=idx,
            )

        last_turn = turns[-1]
        return FlowExecutionResult(
            stopped_by="sequence_complete",
            turns=turns,
            final_output=last_turn.raw_output,
            final_agent=self.config.agent_order[-1],
        )
