from __future__ import annotations

from typing import Any, Callable, Optional

from .core import BackendTool, ToolResult, json_result
from .runtime_shared import schema


def create_agents_list_tool(list_agents: Optional[Callable[[], Any]] = None) -> BackendTool:
    """List agent ids allowed for subagent spawning."""

    def execute(_params: dict[str, Any]) -> ToolResult:
        if list_agents is None:
            return json_result({"requester": "default", "allowAny": True, "agents": []})
        return json_result(list_agents())

    return BackendTool(
        name="agents_list",
        label="Agents",
        description='List agent ids allowed for sessions_spawn runtime="subagent".',
        parameters=schema({}),
        execute=execute,
    )
