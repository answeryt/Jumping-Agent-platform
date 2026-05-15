# -*- coding: utf-8 -*-
"""Context compaction primitives for backend working memory."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

ChatMessage = dict[str, str]

MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000
AUTOCOMPACT_BUFFER_TOKENS = 13_000
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
ERROR_THRESHOLD_BUFFER_TOKENS = 20_000
MANUAL_COMPACT_BUFFER_TOKENS = 3_000
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3

DEFAULT_CONTEXT_WINDOW = 200_000
DEFAULT_MAX_OUTPUT_TOKENS = 64_000
COMPACT_SUMMARY_ROLE = "system"
COMPACT_BOUNDARY_MARKER = "[context compacted]"


@dataclass(frozen=True)
class AutoCompactTrackingState:
    """State threaded across automatic compaction attempts."""

    compacted: bool = False
    turn_counter: int = 0
    turn_id: str = ""
    consecutive_failures: int = 0


@dataclass(frozen=True)
class SessionMemoryCompactConfig:
    """How much recent conversation to preserve after compaction."""

    min_tokens: int = 10_000
    min_text_block_messages: int = 5
    max_tokens: int = 40_000


@dataclass(frozen=True)
class TokenWarningState:
    percent_left: int
    is_above_warning_threshold: bool
    is_above_error_threshold: bool
    is_above_auto_compact_threshold: bool
    is_at_blocking_limit: bool


@dataclass(frozen=True)
class CompactionResult:
    summary_message: ChatMessage
    messages_to_keep: list[ChatMessage]
    pre_compact_token_count: int
    post_compact_token_count: int
    last_summarized_id: str | None
    was_session_memory_compaction: bool


def _env_truthy(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def estimate_text_tokens(text: str) -> int:
    """Rough token estimate matching the TS fallback: about 4 chars/token."""

    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def estimate_message_tokens(messages: Iterable[ChatMessage]) -> int:
    total = 0
    for message in messages:
        total += estimate_text_tokens(message.get("role", ""))
        total += estimate_text_tokens(message.get("content", ""))
        total += 4
    return total


def get_effective_context_window_size(
    *,
    context_window: int | None = None,
    max_output_tokens: int | None = None,
) -> int:
    """Return context window minus reserved summary-output headroom."""

    env_window = _env_int("AGENT_AUTO_COMPACT_WINDOW", DEFAULT_CONTEXT_WINDOW)
    env_output = _env_int("AGENT_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)
    actual_window = context_window or env_window
    output_cap = max_output_tokens or env_output

    override = os.getenv("CLAUDE_CODE_AUTO_COMPACT_WINDOW")
    if override:
        try:
            parsed = int(override)
        except ValueError:
            parsed = 0
        if parsed > 0:
            actual_window = parsed

    reserved = min(output_cap, MAX_OUTPUT_TOKENS_FOR_SUMMARY)
    return max(1, actual_window - reserved)


def get_auto_compact_threshold(
    *,
    context_window: int | None = None,
    max_output_tokens: int | None = None,
) -> int:
    effective_window = get_effective_context_window_size(
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )
    threshold = effective_window - AUTOCOMPACT_BUFFER_TOKENS

    env_percent = os.getenv("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")
    if env_percent:
        try:
            parsed = float(env_percent)
        except ValueError:
            parsed = 0.0
        if 0 < parsed <= 100:
            percentage_threshold = math.floor(effective_window * (parsed / 100))
            return max(1, min(percentage_threshold, threshold))

    return max(1, threshold)


def is_auto_compact_enabled() -> bool:
    if _env_truthy("DISABLE_COMPACT") or _env_truthy("DISABLE_AUTO_COMPACT"):
        return False
    if _env_truthy("AGENT_DISABLE_AUTO_COMPACT"):
        return False
    return True


def calculate_token_warning_state(
    token_usage: int,
    *,
    context_window: int | None = None,
    max_output_tokens: int | None = None,
) -> TokenWarningState:
    auto_threshold = get_auto_compact_threshold(
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )
    effective_window = get_effective_context_window_size(
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )
    threshold = auto_threshold if is_auto_compact_enabled() else effective_window
    percent_left = max(0, round(((threshold - token_usage) / threshold) * 100))
    warning_threshold = threshold - WARNING_THRESHOLD_BUFFER_TOKENS
    error_threshold = threshold - ERROR_THRESHOLD_BUFFER_TOKENS

    default_blocking_limit = effective_window - MANUAL_COMPACT_BUFFER_TOKENS
    blocking_limit = _env_int(
        "CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE",
        default_blocking_limit,
    )

    return TokenWarningState(
        percent_left=percent_left,
        is_above_warning_threshold=token_usage >= warning_threshold,
        is_above_error_threshold=token_usage >= error_threshold,
        is_above_auto_compact_threshold=(
            is_auto_compact_enabled() and token_usage >= auto_threshold
        ),
        is_at_blocking_limit=token_usage >= blocking_limit,
    )


def should_auto_compact(
    messages: list[ChatMessage],
    *,
    snip_tokens_freed: int = 0,
    context_window: int | None = None,
    max_output_tokens: int | None = None,
) -> bool:
    if not is_auto_compact_enabled():
        return False

    token_count = estimate_message_tokens(messages) - snip_tokens_freed
    warning_state = calculate_token_warning_state(
        token_count,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )
    return warning_state.is_above_auto_compact_threshold


def has_text_blocks(message: ChatMessage) -> bool:
    return bool(str(message.get("content", "")).strip())


def calculate_messages_to_keep_index(
    messages: list[ChatMessage],
    last_summarized_index: int,
    config: SessionMemoryCompactConfig | None = None,
) -> int:
    """Calculate the preserved suffix start index after compaction."""

    if not messages:
        return 0

    cfg = config or SessionMemoryCompactConfig()
    start_index = (
        last_summarized_index + 1
        if last_summarized_index >= 0
        else len(messages)
    )

    total_tokens = estimate_message_tokens(messages[start_index:])
    text_count = sum(1 for msg in messages[start_index:] if has_text_blocks(msg))

    if total_tokens >= cfg.max_tokens:
        return start_index
    if total_tokens >= cfg.min_tokens and text_count >= cfg.min_text_block_messages:
        return start_index

    for index in range(start_index - 1, -1, -1):
        message = messages[index]
        total_tokens += estimate_message_tokens([message])
        if has_text_blocks(message):
            text_count += 1
        start_index = index

        if total_tokens >= cfg.max_tokens:
            break
        if total_tokens >= cfg.min_tokens and text_count >= cfg.min_text_block_messages:
            break

    return start_index


def build_compact_summary(
    messages_to_summarize: list[ChatMessage],
    *,
    previous_summary: str = "",
    max_tokens: int = 8_000,
) -> str:
    """Create a deterministic compact summary from older messages."""

    now = datetime.now(timezone.utc).isoformat()
    sections: list[str] = [
        COMPACT_BOUNDARY_MARKER,
        f"Updated at: {now}",
    ]
    if previous_summary.strip():
        sections.extend(["", "Previous session memory:", previous_summary.strip()])

    if messages_to_summarize:
        sections.extend(["", "Conversation covered by this compaction:"])
        budget = max_tokens - estimate_text_tokens("\n".join(sections))
        lines: list[str] = []
        # Keep the most recent older messages because they are usually the most
        # useful bridge into the preserved tail.
        for message in reversed(messages_to_summarize):
            role = message.get("role", "unknown")
            content = " ".join(message.get("content", "").split())
            if not content:
                continue
            line = f"- {role}: {content}"
            line_tokens = estimate_text_tokens(line)
            if lines and budget - line_tokens <= 0:
                break
            lines.append(line)
            budget -= line_tokens
        sections.extend(reversed(lines))

    return "\n".join(sections).strip()


def create_summary_message(summary: str) -> ChatMessage:
    return {
        "role": COMPACT_SUMMARY_ROLE,
        "content": (
            "The earlier conversation has been compacted into this session "
            f"memory summary.\n\n{summary}"
        ),
    }


def compact_conversation(
    messages: list[ChatMessage],
    *,
    previous_summary: str = "",
    last_summarized_id: str | None = None,
    config: SessionMemoryCompactConfig | None = None,
) -> CompactionResult | None:
    """Compact messages into a summary plus a preserved suffix."""

    if not messages:
        return None

    message_ids = [msg.get("id", "") for msg in messages]
    if last_summarized_id and last_summarized_id in message_ids:
        last_summarized_index = message_ids.index(last_summarized_id)
        was_session_memory_compaction = bool(previous_summary.strip())
    elif previous_summary.strip():
        last_summarized_index = len(messages) - 1
        was_session_memory_compaction = True
    else:
        last_summarized_index = -1
        was_session_memory_compaction = False

    start_index = calculate_messages_to_keep_index(
        messages,
        last_summarized_index,
        config,
    )
    messages_to_summarize = messages[:start_index]
    messages_to_keep = messages[start_index:]
    if not messages_to_summarize and previous_summary.strip():
        return None

    summary = build_compact_summary(
        messages_to_summarize,
        previous_summary=previous_summary,
    )
    summary_message = create_summary_message(summary)
    post_messages = [summary_message, *messages_to_keep]

    summarized_tail = (
        messages_to_summarize[-1].get("id") if messages_to_summarize else None
    )
    return CompactionResult(
        summary_message=summary_message,
        messages_to_keep=messages_to_keep,
        pre_compact_token_count=estimate_message_tokens(messages),
        post_compact_token_count=estimate_message_tokens(post_messages),
        last_summarized_id=summarized_tail,
        was_session_memory_compaction=was_session_memory_compaction,
    )


def auto_compact_if_needed(
    messages: list[ChatMessage],
    *,
    previous_summary: str = "",
    last_summarized_id: str | None = None,
    tracking: AutoCompactTrackingState | None = None,
    config: SessionMemoryCompactConfig | None = None,
    context_window: int | None = None,
    max_output_tokens: int | None = None,
) -> CompactionResult | None:
    """Run automatic compaction if the threshold is exceeded."""

    state = tracking or AutoCompactTrackingState()
    if state.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        return None

    threshold_messages = (
        [create_summary_message(previous_summary)]
        if previous_summary.strip()
        else []
    ) + messages
    if not should_auto_compact(
        threshold_messages,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    ):
        return None

    result = compact_conversation(
        messages,
        previous_summary=previous_summary,
        last_summarized_id=last_summarized_id,
        config=config,
    )
    if result is None:
        return None

    threshold = get_auto_compact_threshold(
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )
    if result.post_compact_token_count >= threshold and previous_summary.strip():
        # Same fallback as the TS path: if session-memory compaction cannot
        # create enough headroom, retry without trusting the existing summary.
        return compact_conversation(
            messages,
            previous_summary="",
            last_summarized_id=None,
            config=config,
        )

    return result
