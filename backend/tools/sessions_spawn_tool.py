from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, read_string
from .runtime_shared import GatewayCaller, gateway_result, schema, string_enum, timeout_ms


def create_sessions_spawn_tool(gateway: Optional[GatewayCaller] = None) -> BackendTool:
    """Spawn subagent/ACP runtime sessions."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        read_string(params, "task", required=True)
        return gateway_result(gateway, "sessions_spawn", "sessions.spawn", params, timeout_ms(params))

    return BackendTool(
        name="sessions_spawn",
        label="Sessions",
        display_summary="Spawn subagent sessions.",
        description="Spawn subagent/ACP runtime sessions with task, model, cwd, thread, attachments, and timeout options.",
        parameters=schema(
            {
                "task": {"type": "string"},
                "taskName": {"type": "string"},
                "label": {"type": "string"},
                "runtime": string_enum(["subagent", "acp"]),
                "agentId": {"type": "string"},
                "model": {"type": "string"},
                "thinking": {"type": "string"},
                "cwd": {"type": "string"},
                "mode": string_enum(["run", "session"]),
                "context": string_enum(["fork", "isolated"]),
                "attachments": {"type": "array"},
                "timeoutSeconds": {"type": "number"},
                "runTimeoutSeconds": {"type": "number"},
            },
            ["task"],
        ),
        execute=execute,
    )
