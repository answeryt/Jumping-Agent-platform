"""
flow_template/common.py

公共 Flow 模板片段。
用于生成各类 Flow Python 骨架中的共享 import 和 parser 代码。
"""

from __future__ import annotations



def parser_class(flow_type: str, extra_fields: str = "") -> str:
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


COMMON_IMPORTS = '''from __future__ import annotations

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
'''


ASYNC_IMPORTS = '''import asyncio
'''
