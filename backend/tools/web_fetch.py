from __future__ import annotations

import urllib.request
from typing import Any, Dict

from .core import BackendTool, ToolResult, json_result, read_number, read_string
from .runtime_shared import html_to_text, schema, string_enum


def create_web_fetch_tool() -> BackendTool:
    """Fetch URL and extract readable text/markdown."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        url = read_string(params, "url", required=True)
        extract_mode = read_string(params, "extractMode") or "markdown"
        max_chars = int(read_number(params, "maxChars", integer=True) or 12000)
        timeout = int(read_number(params, "timeoutSeconds", integer=True) or 20)
        request = urllib.request.Request(url, headers={"User-Agent": "OpenClawBackendTools/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024)
            charset = response.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            final_url = response.geturl()
            status = getattr(response, "status", None)
            content_type = response.headers.get("content-type")

        text = html_to_text(body) if "html" in (content_type or "").lower() else body
        extracted = text[:max_chars]
        truncated = len(text) > max_chars
        if truncated:
            extracted += "\n...(truncated)..."
        return json_result(
            {
                "url": url,
                "finalUrl": final_url,
                "status": status,
                "contentType": content_type,
                "extractMode": extract_mode,
                "text": extracted,
                "truncated": truncated,
            }
        )

    return BackendTool(
        name="web_fetch",
        label="Web Fetch",
        description="Fetch URL and extract readable markdown/text. Lightweight page access; no browser automation.",
        parameters=schema(
            {
                "url": {"type": "string"},
                "extractMode": string_enum(["markdown", "text"]),
                "maxChars": {"type": "number"},
                "timeoutSeconds": {"type": "number"},
            },
            ["url"],
        ),
        execute=execute,
    )
