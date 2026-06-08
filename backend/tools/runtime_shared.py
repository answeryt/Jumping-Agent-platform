from __future__ import annotations

import html
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from .core import ToolResult, json_result, read_number


GatewayCaller = Callable[[str, Dict[str, Any], Optional[int]], Any]
ProviderCaller = Callable[[Dict[str, Any]], Any]


def schema(properties: Dict[str, Any], required: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required or []),
    }


def string_enum(values: Iterable[str]) -> Dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def timeout_ms(params: Dict[str, Any]) -> Optional[int]:
    value = read_number(params, "timeoutMs", integer=True)
    return int(value) if value is not None else None


def require_gateway(gateway: Optional[GatewayCaller], tool_name: str) -> GatewayCaller:
    if gateway is None:
        raise RuntimeError(f"{tool_name} requires a gateway caller")
    return gateway


def gateway_result(
    gateway: Optional[GatewayCaller],
    tool_name: str,
    method: str,
    params: Dict[str, Any],
    timeout: Optional[int] = None,
) -> ToolResult:
    caller = require_gateway(gateway, tool_name)
    return json_result(caller(method, params, timeout))


def html_to_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", body)
    body = re.sub(r"(?is)<br\s*/?>", "\n", body)
    body = re.sub(r"(?is)</p\s*>", "\n\n", body)
    body = re.sub(r"(?is)<.*?>", "", body)
    body = html.unescape(body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return "\n".join(line.strip() for line in body.splitlines() if line.strip())


@dataclass
class MediaTaskRegistry:
    tasks: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def start(
        self,
        tool_name: str,
        params: Dict[str, Any],
        provider: Optional[ProviderCaller],
    ) -> Dict[str, Any]:
        task_id = uuid.uuid4().hex
        task = {
            "taskId": task_id,
            "tool": tool_name,
            "status": "started",
            "createdAt": time.time(),
            "params": params,
        }
        self.tasks[task_id] = task
        if provider is not None:
            try:
                task["result"] = provider(params)
                task["status"] = "completed"
            except Exception as exc:
                task["status"] = "failed"
                task["error"] = str(exc)
        return task

    def active(self, tool_name: str) -> List[Dict[str, Any]]:
        return [
            task
            for task in self.tasks.values()
            if task.get("tool") == tool_name and task.get("status") == "started"
        ]


MEDIA_TASKS = MediaTaskRegistry()

