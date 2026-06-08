from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .core import BackendTool, ToolResult, json_result
from .runtime_shared import schema, string_enum


def create_subagents_tool(list_runs: Optional[Callable[[Dict[str, Any]], Any]] = None) -> BackendTool:
    """List active and recent subagents for the requester session."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        if list_runs is None:
            return json_result({"status": "ok", "action": "list", "active": [], "recent": [], "total": 0})
        return json_result(list_runs(params))

    return BackendTool(
        name="subagents",
        label="Subagents",
        description="List active and recent subagents for the requester session.",
        parameters=schema({"action": string_enum(["list"]), "recentMinutes": {"type": "number"}}),
        execute=execute,
    )
