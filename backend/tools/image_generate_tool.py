from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, json_result, read_string, text_result
from .runtime_shared import MEDIA_TASKS, ProviderCaller, schema


def create_image_generate_tool(provider: Optional[ProviderCaller] = None) -> BackendTool:
    """Create or edit images, optionally via background-style task tracking."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        action = read_string(params, "action") or "generate"
        if action == "list":
            return json_result({"providers": [], "configured": provider is not None})
        if action == "status":
            return json_result({"status": "ok", "active": MEDIA_TASKS.active("image_generate")})
        prompt = read_string(params, "prompt", required=True)
        task = MEDIA_TASKS.start("image_generate", {**params, "prompt": prompt}, provider)
        return text_result(
            f"Background task started for image generation ({task['taskId']}).",
            {"async": True, "status": task["status"], "taskId": task["taskId"], "task": task},
            terminate=True,
        )

    return BackendTool(
        name="image_generate",
        label="Image Generation",
        description="Create/edit images. Use list for providers/models/readiness/auth and status for active task.",
        parameters=schema(
            {
                "action": {"type": "string"},
                "prompt": {"type": "string"},
                "image": {"type": "string"},
                "images": {"type": "array"},
                "model": {"type": "string"},
                "filename": {"type": "string"},
                "size": {"type": "string"},
                "aspectRatio": {"type": "string"},
                "resolution": {"type": "string"},
                "quality": {"type": "string"},
                "outputFormat": {"type": "string"},
                "background": {"type": "string"},
            }
        ),
        execute=execute,
    )
