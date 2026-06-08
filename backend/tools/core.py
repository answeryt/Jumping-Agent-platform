from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


ToolExecute = Callable[[Dict[str, Any]], Any]


class ToolInputError(ValueError):
    """Raised when a model/tool caller provides invalid arguments."""


@dataclass
class ToolResult:
    """Small Python equivalent of the TS AgentToolResult shape."""

    content: List[Dict[str, Any]] = field(default_factory=list)
    details: Any = None
    terminate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"content": self.content, "details": self.details}
        if self.terminate:
            payload["terminate"] = True
        return payload


@dataclass
class BackendTool:
    """Runtime-neutral tool definition used by backend agents."""

    name: str
    description: str
    execute: ToolExecute
    parameters: Dict[str, Any] = field(default_factory=dict)
    label: Optional[str] = None
    display_summary: Optional[str] = None

    def run(self, **kwargs: Any) -> Dict[str, Any]:
        result = self.execute(kwargs)
        if isinstance(result, ToolResult):
            return result.to_dict()
        if isinstance(result, dict) and "content" in result and "details" in result:
            return result
        return json_result(result).to_dict()


def as_params(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def read_string(
    params: Dict[str, Any],
    key: str,
    *,
    required: bool = False,
    allow_empty: bool = False,
    trim: bool = True,
) -> Optional[str]:
    raw = params.get(key)
    if not isinstance(raw, str):
        if required:
            raise ToolInputError(f"{key} required")
        return None
    value = raw.strip() if trim else raw
    if not value and not allow_empty:
        if required:
            raise ToolInputError(f"{key} required")
        return None
    return value


def read_number(
    params: Dict[str, Any],
    key: str,
    *,
    required: bool = False,
    integer: bool = False,
) -> Optional[float]:
    raw = params.get(key)
    value: Optional[float] = None
    if isinstance(raw, bool):
        value = None
    elif isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            value = float(raw.strip())
        except ValueError:
            value = None
    if value is None:
        if required:
            raise ToolInputError(f"{key} required")
        return None
    return int(value) if integer else value


def text_result(text: str, details: Any = None, *, terminate: bool = False) -> ToolResult:
    return ToolResult(
        content=[{"type": "text", "text": text}],
        details=details if details is not None else {"text": text},
        terminate=terminate,
    )


def json_result(payload: Any, *, terminate: bool = False) -> ToolResult:
    return ToolResult(
        content=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2, default=str)}],
        details=payload,
        terminate=terminate,
    )

