from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolInputError, ToolResult, json_result
from .runtime_shared import ProviderCaller, schema


def create_pdf_tool(provider: Optional[ProviderCaller] = None) -> BackendTool:
    """Analyze PDFs with a model."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        if not params.get("pdf") and not params.get("pdfs"):
            raise ToolInputError("pdf or pdfs required")
        if provider is None:
            return json_result({"status": "error", "error": "No provider configured for pdf."})
        return json_result(provider(params))

    return BackendTool(
        name="pdf",
        label="PDF",
        description="Analyze PDFs with model. Native PDF provider when supported; otherwise provider may extract text/images.",
        parameters=schema(
            {
                "prompt": {"type": "string"},
                "pdf": {"type": "string"},
                "pdfs": {"type": "array", "items": {"type": "string"}},
                "pages": {"type": "string"},
                "model": {"type": "string"},
                "maxBytesMb": {"type": "number"},
                "maxPages": {"type": "number"},
            }
        ),
        execute=execute,
    )
