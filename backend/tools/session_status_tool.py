from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult
from .runtime_shared import GatewayCaller, gateway_result, schema, timeout_ms


def create_session_status_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """Read or update session status/model."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        return gateway_result(gateway, "session_status", "sessions.status", params, timeout_ms(params))

    return BackendTool(
        name="session_status",
        label="Session Status",
        display_summary="Read or update session status.",
        description="Read or update session status/model. Supports current session semantics when backend gateway implements it.",
        parameters=schema({"sessionKey": {"type": "string"}, "model": {"type": "string"}}),
        execute=execute,
    )
