from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult
from .runtime_shared import GatewayCaller, gateway_result, schema, timeout_ms


def create_sessions_list_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """List visible sessions."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        return gateway_result(gateway, "sessions_list", "sessions.list", params, timeout_ms(params))

    return BackendTool(
        name="sessions_list",
        label="Sessions",
        display_summary="List sessions.",
        description="List visible sessions with optional filters and summary fields.",
        parameters=schema(
            {
                "kinds": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "number"},
                "activeMinutes": {"type": "number"},
                "messageLimit": {"type": "number"},
                "label": {"type": "string"},
                "agentId": {"type": "string"},
                "search": {"type": "string"},
                "includeDerivedTitles": {"type": "boolean"},
                "includeLastMessage": {"type": "boolean"},
            }
        ),
        execute=execute,
    )
