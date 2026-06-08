from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, json_result, read_string, text_result
from .runtime_shared import MEDIA_TASKS, ProviderCaller, schema


def create_music_generate_tool(provider: Optional[ProviderCaller] = None) -> BackendTool:
    """Create audio/music for songs, beats, loops, soundtracks, or instrumentals."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        action = read_string(params, "action") or "generate"
        if action == "list":
            return json_result({"providers": [], "configured": provider is not None})
        if action == "status":
            return json_result({"status": "ok", "active": MEDIA_TASKS.active("music_generate")})
        prompt = read_string(params, "prompt", required=True)
        task = MEDIA_TASKS.start("music_generate", {**params, "prompt": prompt}, provider)
        return text_result(
            f"Background task started for music generation ({task['taskId']}).",
            {"async": True, "status": task["status"], "taskId": task["taskId"], "task": task},
            terminate=True,
        )

    return BackendTool(
        name="music_generate",
        label="Music Generation",
        display_summary="Generate music",
        description="Create audio/music for song, jingle, beat, loop, soundtrack, anthem, instrumental requests.",
        parameters=schema(
            {
                "action": {"type": "string"},
                "prompt": {"type": "string"},
                "lyrics": {"type": "string"},
                "instrumental": {"type": "boolean"},
                "model": {"type": "string"},
                "durationSeconds": {"type": "number"},
                "format": {"type": "string"},
                "filename": {"type": "string"},
                "image": {"type": "string"},
                "images": {"type": "array"},
            }
        ),
        execute=execute,
    )
