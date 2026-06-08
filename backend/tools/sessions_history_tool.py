from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, read_string
from .runtime_shared import GatewayCaller, gateway_result, schema, timeout_ms


def create_sessions_history_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """Read sanitized session history."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        read_string(params, "sessionKey", required=True)
        return gateway_result(gateway, "sessions_history", "chat.history", params, timeout_ms(params))

    return BackendTool(
        name="sessions_history",
        label="Session History",
        display_summary="Read session history.",
        description="Read sanitized session history. Tool messages are excluded unless includeTools=true.",
        parameters=schema(
            {
                "sessionKey": {"type": "string"},
                "limit": {"type": "number"},
                "includeTools": {"type": "boolean"},
            },
            ["sessionKey"],
        ),
        execute=execute,
    )
