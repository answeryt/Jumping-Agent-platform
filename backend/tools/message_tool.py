from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, read_string
from .runtime_shared import GatewayCaller, gateway_result, schema, timeout_ms


def strip_reasoning_tags(text: str) -> str:
    return re.sub(r"(?is)<think>.*?</think>", "", text).strip()


def create_message_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """Send and manage messages across configured channels."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        action = read_string(params, "action", required=True)
        payload = dict(params)
        payload.pop("action", None)
        for field in ("text", "content", "message", "caption"):
            if isinstance(payload.get(field), str):
                payload[field] = strip_reasoning_tags(payload[field])
        method = "send" if action == "send" else f"message.{action}"
        return gateway_result(gateway, "message", method, payload, timeout_ms(params))

    return BackendTool(
        name="message",
        label="Message",
        display_summary="Send and manage messages across configured channels.",
        description="Send and manage messages across configured channels.",
        parameters=schema(
            {
                "action": {"type": "string"},
                "text": {"type": "string"},
                "message": {"type": "string"},
                "content": {"type": "string"},
                "caption": {"type": "string"},
                "to": {"type": "string"},
                "target": {"type": "string"},
                "channel": {"type": "string"},
                "threadId": {"type": "string"},
                "attachments": {"type": "array"},
                "presentation": {"type": "object"},
            },
            ["action"],
        ),
        execute=execute,
    )
