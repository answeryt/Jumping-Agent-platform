from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolInputError, ToolResult, read_string
from .runtime_shared import GatewayCaller, gateway_result, schema, string_enum, timeout_ms


NODES_TOOL_ACTIONS = [
    "status",
    "describe",
    "pending",
    "approve",
    "reject",
    "notify",
    "camera_snap",
    "camera_list",
    "camera_clip",
    "photos_latest",
    "screen_record",
    "location_get",
    "notifications_list",
    "notifications_action",
    "device_status",
    "device_info",
    "device_permissions",
    "device_health",
    "invoke",
]


def create_nodes_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """Discover/control paired nodes."""

    method_map = {
        "status": "node.list",
        "describe": "node.describe",
        "pending": "node.pair.list",
        "approve": "node.pair.approve",
        "reject": "node.pair.reject",
    }

    def execute(params: Dict[str, Any]) -> ToolResult:
        action = read_string(params, "action", required=True)
        if action not in NODES_TOOL_ACTIONS:
            raise ToolInputError("unsupported nodes action")
        method = method_map.get(action, "node.invoke")
        payload = {key: value for key, value in params.items() if key != "action"}
        if method == "node.invoke":
            payload.setdefault("command", action)
        return gateway_result(gateway, "nodes", method, payload, timeout_ms(params))

    return BackendTool(
        name="nodes",
        label="Nodes",
        description="Discover/control paired nodes: status, describe, pairing, notify, camera/photos/screen/location/notifications/invoke.",
        parameters=schema(
            {
                "action": string_enum(NODES_TOOL_ACTIONS),
                "node": {"type": "string"},
                "requestId": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "command": {"type": "string"},
                "params": {"type": "object"},
                "timeoutMs": {"type": "number"},
            },
            ["action"],
        ),
        execute=execute,
    )

