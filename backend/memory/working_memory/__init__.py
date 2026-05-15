# -*- coding: utf-8 -*-
"""Backend short-term memory package.

Use AgentWorkingMemory for generated Agent flows. The async SQLAlchemy backend
is kept as the lower-level persistent implementation.
"""

from ._agent_working_memory import AgentWorkingMemory, ChatMessage
from ._base import MemoryBase, Msg
from ._context_compaction import (
    AutoCompactTrackingState,
    CompactionResult,
    SessionMemoryCompactConfig,
    TokenWarningState,
    auto_compact_if_needed,
    calculate_messages_to_keep_index,
    calculate_token_warning_state,
    compact_conversation,
    estimate_message_tokens,
    get_auto_compact_threshold,
    get_effective_context_window_size,
    should_auto_compact,
)
from ..memory_template_writer import AgentOutputRecord, update_memory_template

try:
    from ._sqlalchemy_memory import AsyncSQLAlchemyMemory
except ImportError:  # SQLAlchemy is optional for the lightweight facade.
    AsyncSQLAlchemyMemory = None  # type: ignore[assignment]

__all__ = [
    "AgentWorkingMemory",
    "AgentOutputRecord",
    "AsyncSQLAlchemyMemory",
    "AutoCompactTrackingState",
    "ChatMessage",
    "CompactionResult",
    "MemoryBase",
    "Msg",
    "SessionMemoryCompactConfig",
    "TokenWarningState",
    "auto_compact_if_needed",
    "calculate_messages_to_keep_index",
    "calculate_token_warning_state",
    "compact_conversation",
    "estimate_message_tokens",
    "get_auto_compact_threshold",
    "get_effective_context_window_size",
    "should_auto_compact",
    "update_memory_template",
]
