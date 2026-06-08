from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, read_string
from .runtime_shared import GatewayCaller, gateway_result, schema, timeout_ms


def create_sessions_send_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """Send a message to another session."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        read_string(params, "message", required=True)
        return gateway_result(gateway, "sessions_send", "agent", params, timeout_ms(params))

    return BackendTool(
        name="sessions_send",
        label="Session Send",
        display_summary="Send message to session.",
        description="Send a message to a session by sessionKey or label and wait for agent reply when backend supports it.",
        parameters=schema(
            {
                "sessionKey": {"type": "string"},
                "label": {"type": "string"},
                "agentId": {"type": "string"},
                "message": {"type": "string"},
                "timeoutSeconds": {"type": "number"},
            },
            ["message"],
        ),
        execute=execute,
    )
