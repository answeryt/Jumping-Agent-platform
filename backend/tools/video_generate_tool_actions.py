from __future__ import annotations

from .media_generate_tool_actions_shared import (
    create_media_generate_provider_list_action_result as create_video_generate_list_action_result,
    create_media_generate_task_status_actions as create_video_generate_status_action_result,
)


def create_video_generate_duplicate_guard_result(*_args, **_kwargs):
    return None


__all__ = [
    "create_video_generate_duplicate_guard_result",
    "create_video_generate_list_action_result",
    "create_video_generate_status_action_result",
]

