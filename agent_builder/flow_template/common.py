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


ASYNC_IMPORTS = '''import asyncio
'''
