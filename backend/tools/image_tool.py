from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolInputError, ToolResult, json_result
from .runtime_shared import ProviderCaller, schema


def create_image_tool(provider: Optional[ProviderCaller] = None) -> BackendTool:
    """Analyze images with a vision model."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        if not params.get("image") and not params.get("images"):
            raise ToolInputError("image or images required")
        if provider is None:
            return json_result({"status": "error", "error": "No provider configured for image."})
        return json_result(provider(params))

    return BackendTool(
        name="image",
        label="Image",
        description="Analyze images with vision model. Use image for one path/URL, images for multiple inputs.",
        parameters=schema(
            {
                "prompt": {"type": "string"},
                "image": {"type": "string"},
                "images": {"type": "array", "items": {"type": "string"}},
                "model": {"type": "string"},
                "maxBytesMb": {"type": "number"},
                "maxImages": {"type": "number"},
            }
        ),
        execute=execute,
    )
