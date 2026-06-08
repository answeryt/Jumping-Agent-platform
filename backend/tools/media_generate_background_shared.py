from __future__ import annotations

from typing import Any, Callable, Dict, Optional


MediaGenerateBackgroundScheduler = Callable[[Callable[[], Any]], None]


def create_default_media_generate_background_scheduler(
    *,
    tool_name: str,
    on_crash: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
) -> MediaGenerateBackgroundScheduler:
    def schedule(work: Callable[[], Any]) -> None:
        try:
            work()
        except Exception as exc:
            if on_crash:
                on_crash(f"Detached {tool_name} job crashed", {"error": exc})
            else:
                raise

    return schedule


def build_media_generation_started_tool_result(
    *,
    tool_name: str,
    generation_label: str,
    completion_label: str,
    task_handle: Optional[Dict[str, Any]] = None,
    detail_extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task_id = (task_handle or {}).get("taskId", "unknown")
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Background task started for {generation_label} generation ({task_id}). "
                    f"Do not call {tool_name} again for this request. Wait for the completion event; "
                    f"the completion agent will send the finished {completion_label} here when ready."
                ),
            }
        ],
        "details": {"async": True, "status": "started", **(task_handle or {}), **(detail_extras or {})},
        "terminate": True,
    }


__all__ = [
    "MediaGenerateBackgroundScheduler",
    "build_media_generation_started_tool_result",
    "create_default_media_generate_background_scheduler",
]

