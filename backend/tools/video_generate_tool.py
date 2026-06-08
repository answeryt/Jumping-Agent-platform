from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, json_result, read_string, text_result
from .runtime_shared import MEDIA_TASKS, ProviderCaller, schema


def create_video_generate_tool(provider: Optional[ProviderCaller] = None) -> BackendTool:
    """Create videos with optional references and provider-specific options."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        action = read_string(params, "action") or "generate"
        if action == "list":
            return json_result({"providers": [], "configured": provider is not None})
        if action == "status":
            return json_result({"status": "ok", "active": MEDIA_TASKS.active("video_generate")})
        prompt = read_string(params, "prompt", required=True)
        task = MEDIA_TASKS.start("video_generate", {**params, "prompt": prompt}, provider)
        return text_result(
            f"Background task started for video generation ({task['taskId']}).",
            {"async": True, "status": task["status"], "taskId": task["taskId"], "task": task},
            terminate=True,
        )

    return BackendTool(
        name="video_generate",
        label="Video Generation",
        display_summary="Generate videos",
        description="Create videos. Use status for active task. Duration may round to provider-supported value.",
        parameters=schema(
            {
                "action": {"type": "string"},
                "prompt": {"type": "string"},
                "model": {"type": "string"},
                "filename": {"type": "string"},
                "image": {"type": "string"},
                "images": {"type": "array"},
                "audioReference": {"type": "string"},
                "size": {"type": "string"},
                "aspectRatio": {"type": "string"},
                "resolution": {"type": "string"},
                "durationSeconds": {"type": "number"},
                "audio": {"type": "boolean"},
                "watermark": {"type": "boolean"},
                "providerOptions": {"type": "object"},
            }
        ),
        execute=execute,
    )
