from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from backend.tools.tool_bridge import ToolBridge


@dataclass(frozen=True)
class LSMRepairRequest:
    """A repair message that should be returned to the LLM as feedback."""

    reason: str
    message: str
    original_text: str
    raw_call: Optional[str] = None
    available_tools: List[str] = field(default_factory=list)


class LSMFallbackLayer:
    """Lightweight safety layer for malformed or failed tool calls."""

    def __init__(self, *, max_original_chars: int = 1200, max_tools: int = 40) -> None:
        self.max_original_chars = max_original_chars
        self.max_tools = max_tools

    def diagnose_parse_failure(self, text: str, bridge: ToolBridge) -> str:
        content = text or ""
        if not bridge.contains_tool_call(content):
            return "No tool_call(...) expression was found."

        spans = bridge._extract_call_spans(content)
        if not spans:
            return "A tool_call( marker was found, but its parentheses or string quotes are not balanced."

        errors: List[str] = []
        for raw_call in spans:
            try:
                bridge._parse_single_call(raw_call)
            except ValueError as exc:
                errors.append(str(exc))
                syntax_error = self._syntax_error(raw_call)
                if syntax_error:
                    errors.append(syntax_error)
        if errors:
            return " ".join(dict.fromkeys(errors))
        return "tool_call(...) could not be parsed into a valid tool invocation."

    def parse_error(
        self,
        *,
        text: str,
        bridge: ToolBridge,
        available_tools: Iterable[str],
    ) -> LSMRepairRequest:
        reason = self.diagnose_parse_failure(text, bridge)
        return LSMRepairRequest(
            reason="parse_error",
            message=self._repair_message(
                title="TOOL_CALL_PARSE_ERROR",
                detail=reason,
                original_text=text,
                available_tools=available_tools,
            ),
            original_text=text,
            available_tools=self._tool_list(available_tools),
        )

    def unknown_tool(
        self,
        *,
        tool_name: str,
        raw_call: str,
        original_text: str,
        available_tools: Iterable[str],
    ) -> LSMRepairRequest:
        return LSMRepairRequest(
            reason="unknown_tool",
            message=self._repair_message(
                title="UNKNOWN_TOOL",
                detail=f"Tool `{tool_name}` is not registered or is not available to the current agent.",
                original_text=original_text,
                available_tools=available_tools,
                raw_call=raw_call,
            ),
            original_text=original_text,
            raw_call=raw_call,
            available_tools=self._tool_list(available_tools),
        )

    def execution_error(
        self,
        *,
        tool_name: str,
        error: Exception,
        raw_call: str,
        original_text: str,
        available_tools: Iterable[str],
    ) -> LSMRepairRequest:
        return LSMRepairRequest(
            reason="execution_error",
            message=self._repair_message(
                title="TOOL_EXECUTION_ERROR",
                detail=f"Tool `{tool_name}` failed with: {type(error).__name__}: {error}",
                original_text=original_text,
                available_tools=available_tools,
                raw_call=raw_call,
            ),
            original_text=original_text,
            raw_call=raw_call,
            available_tools=self._tool_list(available_tools),
        )

    def _repair_message(
        self,
        *,
        title: str,
        detail: str,
        original_text: str,
        available_tools: Iterable[str],
        raw_call: Optional[str] = None,
    ) -> str:
        tools = ", ".join(self._tool_list(available_tools)) or "none"
        original = self._clip(original_text)
        parts = [
            f"Observation: [{title}] {detail}",
            "Please correct the tool call and try again.",
            'Required format: tool_call("tool_name", key="value") or tool_call(tool_name="tool_name", key="value").',
            "Use keyword arguments, quote string values, and prefer forward slashes in Windows paths.",
            f"Available tools: {tools}",
        ]
        if raw_call:
            parts.append(f"Failed call: {self._clip(raw_call)}")
        parts.append(f"Original model output: {original}")
        return "\n".join(parts)

    def _tool_list(self, available_tools: Iterable[str]) -> List[str]:
        return sorted({str(name).strip() for name in available_tools if str(name).strip()})[: self.max_tools]

    def _clip(self, text: str) -> str:
        value = str(text or "").strip()
        if len(value) <= self.max_original_chars:
            return value
        return f"{value[: self.max_original_chars]} ...[truncated]"

    @staticmethod
    def _syntax_error(raw_call: str) -> Optional[str]:
        try:
            ast.parse(raw_call, mode="eval")
        except SyntaxError as exc:
            return f"Python syntax error at line {exc.lineno}, column {exc.offset}: {exc.msg}."
        return None
