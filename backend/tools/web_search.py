from __future__ import annotations

from typing import Any, Dict, Optional

from .core import BackendTool, ToolResult, json_result, read_string
from .runtime_shared import ProviderCaller, schema


def create_web_search_tool(provider: Optional[ProviderCaller] = None) -> BackendTool:
    """Search web using an injected provider."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        query = read_string(params, "query", required=True)
        if provider is None:
            return json_result(
                {
                    "query": query,
                    "results": [],
                    "error": "No web search provider configured. Inject provider(params) to enable live search.",
                }
            )
        return json_result(provider(params))

    return BackendTool(
        name="web_search",
        label="Web Search",
        description="Search web for current info; returns normalized provider results.",
        parameters=schema(
            {
                "query": {"type": "string"},
                "country": {"type": "string"},
                "language": {"type": "string"},
                "freshness": {"type": "string"},
                "dateAfter": {"type": "string"},
                "dateBefore": {"type": "string"},
            },
            ["query"],
        ),
        execute=execute,
    )
