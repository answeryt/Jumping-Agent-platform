from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolInputError, ToolResult, read_string
from .runtime_shared import GatewayCaller, gateway_result, schema, string_enum, timeout_ms


CRON_ACTIONS = ["status", "list", "get", "add", "update", "remove", "run", "runs", "wake"]
CRON_SCHEDULE_KINDS = ["at", "every", "cron"]
CRON_PAYLOAD_KINDS = ["systemEvent", "agentTurn"]
CRON_DELIVERY_MODES = ["none", "announce", "webhook"]
CRON_WAKE_MODES = ["now", "next-heartbeat"]


def create_cron_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """Manage Gateway cron jobs and wake events."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        action = read_string(params, "action", required=True)
        if action not in CRON_ACTIONS:
            raise ToolInputError("unsupported cron action")
        payload = {key: value for key, value in params.items() if key != "action"}
        return gateway_result(gateway, "cron", f"cron.{action}", payload, timeout_ms(params) or 60000)

    return BackendTool(
        name="cron",
        label="Cron",
        display_summary="Manage scheduled jobs and wake events.",
        description="Manage Gateway cron jobs and wake events: reminders, delayed follow-ups, recurring work.",
        parameters=schema(
            {
                "action": string_enum(CRON_ACTIONS),
                "jobId": {"type": "string"},
                "id": {"type": "string"},
                "job": {"type": "object"},
                "patch": {"type": "object"},
                "text": {"type": "string"},
                "mode": string_enum(CRON_WAKE_MODES),
                "schedule": {"type": "object"},
                "payload": {"type": "object"},
                "delivery": {"type": "object"},
                "timeoutMs": {"type": "number"},
            },
            ["action"],
        ),
        execute=execute,
    )

