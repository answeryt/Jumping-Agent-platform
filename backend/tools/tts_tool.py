from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, json_result, read_string
from .runtime_shared import ProviderCaller, schema


def create_tts_tool(provider: Optional[ProviderCaller] = None) -> BackendTool:
    """Text-to-speech audio tool."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        text = read_string(params, "text", required=True)
        if provider is None:
            return json_result({"success": False, "error": "No TTS provider configured.", "text": text})
        return json_result(provider(params))

    return BackendTool(
        name="tts",
        label="TTS",
        display_summary="Text to speech audio.",
        description="Use only for explicit audio intent or active TTS config. Audio is delivered from tool result details.",
        parameters=schema(
            {"text": {"type": "string"}, "channel": {"type": "string"}, "timeoutMs": {"type": "number"}},
            ["text"],
        ),
        execute=execute,
    )

