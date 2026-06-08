from __future__ import annotations

from typing import Any, Dict

from .core import BackendTool, ToolInputError, ToolResult, json_result, read_string
from .runtime_shared import schema, string_enum


HEARTBEAT_RESPONSE_TOOL_NAME = "heartbeat_respond"
HEARTBEAT_TOOL_OUTCOMES = ["no_change", "progress", "done", "blocked", "needs_attention"]
HEARTBEAT_TOOL_PRIORITIES = ["low", "normal", "high"]


def create_heartbeat_response_tool() -> BackendTool:
    """Record heartbeat result and notification decision."""

    recorded = False

    def execute(params: Dict[str, Any]) -> ToolResult:
        nonlocal recorded
        if recorded:
            raise ToolInputError("heartbeat_respond already recorded for this turn")
        outcome = read_string(params, "outcome", required=True)
        if outcome not in HEARTBEAT_TOOL_OUTCOMES:
            raise ToolInputError("invalid heartbeat outcome")
        if not isinstance(params.get("notify"), bool):
            raise ToolInputError("notify required")
        summary = read_string(params, "summary", required=True)
        priority = read_string(params, "priority")
        if priority and priority not in HEARTBEAT_TOOL_PRIORITIES:
            raise ToolInputError("invalid heartbeat priority")
        recorded = True
        return json_result(
            {
                "status": "recorded",
                "outcome": outcome,
                "notify": params["notify"],
                "summary": summary,
                **({"notificationText": params["notificationText"]} if isinstance(params.get("notificationText"), str) else {}),
                **({"reason": params["reason"]} if isinstance(params.get("reason"), str) else {}),
                **({"priority": priority} if priority else {}),
                **({"nextCheck": params["nextCheck"]} if isinstance(params.get("nextCheck"), str) else {}),
            }
        )

    return BackendTool(
        name=HEARTBEAT_RESPONSE_TOOL_NAME,
        label="Heartbeat",
        display_summary="Record heartbeat outcome/notify choice.",
        description="Record heartbeat result. notify=false no visible send; notify=true needs concise notificationText.",
        parameters=schema(
            {
                "outcome": string_enum(HEARTBEAT_TOOL_OUTCOMES),
                "notify": {"type": "boolean"},
                "summary": {"type": "string"},
                "notificationText": {"type": "string"},
                "reason": {"type": "string"},
                "priority": string_enum(HEARTBEAT_TOOL_PRIORITIES),
                "nextCheck": {"type": "string"},
            },
            ["outcome", "notify", "summary"],
        ),
        execute=execute,
    )

