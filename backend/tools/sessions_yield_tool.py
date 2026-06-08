from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .core import BackendTool, ToolResult, json_result, read_string
from .runtime_shared import schema


def create_sessions_yield_tool(on_yield: Optional[Callable[[str], Any]] = None) -> BackendTool:
    """End current turn and wait for subagent completion."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        message = read_string(params, "message") or "Turn yielded."
        if on_yield is None:
            return json_result({"status": "error", "error": "Yield not supported in this context"})
        on_yield(message)
        return json_result({"status": "yielded", "message": message})

    return BackendTool(
        name="sessions_yield",
        label="Yield",
        description="End current turn. Use after spawning subagents; results arrive as next message.",
        parameters=schema({"message": {"type": "string"}}),
        execute=execute,
    )
