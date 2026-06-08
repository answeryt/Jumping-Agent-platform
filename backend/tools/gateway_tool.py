from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolInputError, ToolResult, read_string
from .runtime_shared import GatewayCaller, gateway_result, schema, string_enum, timeout_ms


GATEWAY_ACTIONS = ["restart", "config.get", "config.schema.lookup", "config.apply", "config.patch", "update.run"]


def create_gateway_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """Gateway restart/config/update tool."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        action = read_string(params, "action", required=True)
        if action not in GATEWAY_ACTIONS:
            raise ToolInputError("unsupported gateway action")
        payload = {key: value for key, value in params.items() if key not in {"action", "timeoutMs"}}
        return gateway_result(gateway, "gateway", f"gateway.{action}", payload, timeout_ms(params))

    return BackendTool(
        name="gateway",
        label="Gateway",
        description="Gateway restart/config/update. Use config.schema.lookup before config edits; prefer config.patch for partial merge.",
        parameters=schema(
            {
                "action": string_enum(GATEWAY_ACTIONS),
                "gatewayUrl": {"type": "string"},
                "gatewayToken": {"type": "string"},
                "raw": {"type": "string"},
                "path": {"type": "string"},
                "note": {"type": "string"},
                "sessionKey": {"type": "string"},
                "timeoutMs": {"type": "number"},
            },
            ["action"],
        ),
        execute=execute,
    )

