from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .core import json_result


def create_media_generate_provider_list_action_result(
    providers: Optional[Iterable[Dict[str, Any]]] = None,
    *,
    configured: bool = False,
) -> Any:
    return json_result({"providers": list(providers or []), "configured": configured})


def create_media_generate_task_status_actions(active: Optional[Iterable[Dict[str, Any]]] = None) -> Any:
    return json_result({"status": "ok", "active": list(active or [])})


__all__ = [
    "create_media_generate_provider_list_action_result",
    "create_media_generate_task_status_actions",
]

