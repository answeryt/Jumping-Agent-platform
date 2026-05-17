# -*- coding: utf-8 -*-
"""Markdown template writer for backend agent context memory.

This module is intentionally append/update-only: it owns the markdown
session-context file format and never decides when a new file is needed or
how much history to keep. Session lifecycle and trimming live in
``backend/memory/working_memory``; callers only pass in a path and the
Agent outputs that should be re-rendered into the AGENT_INFO block.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent / "memory_templete.md"

TASK_OVERVIEW_START = "<!-- TASK_OVERVIEW_START -->"
TASK_OVERVIEW_END = "<!-- TASK_OVERVIEW_END -->"
AGENT_INFO_START = "<!-- AGENT_INFO_START -->"
AGENT_INFO_END = "<!-- AGENT_INFO_END -->"
TOOL_USAGE_START = "<!-- TOOL_USAGE_START -->"
TOOL_USAGE_END = "<!-- TOOL_USAGE_END -->"


@dataclass(frozen=True)
class AgentOutputRecord:
    """One backend agent output to be written into the context template."""

    agent_name: str
    output: str


def _read_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_template(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _replace_between_anchors(
    content: str,
    start_anchor: str,
    end_anchor: str,
    replacement: str,
) -> str:
    start_index = content.find(start_anchor)
    end_index = content.find(end_anchor)
    if start_index == -1 or end_index == -1 or end_index < start_index:
        raise ValueError(f"Template anchor pair not found: {start_anchor} / {end_anchor}")

    before = content[: start_index + len(start_anchor)]
    after = content[end_index:]
    return f"{before}\n{replacement.strip()}\n{after}"


def _replace_line_value(content: str, prefix: str, value: str | int | None) -> str:
    if value is None:
        return content

    lines = content.splitlines()
    value_text = str(value)
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value_text}"
            return "\n".join(lines) + ("\n" if content.endswith("\n") else "")
    raise ValueError(f"Template field not found: {prefix}")


def _format_agent_output(record: AgentOutputRecord) -> str:
    output = record.output.strip()
    if not output:
        output = "暂无输出"
    return "\n".join(
        [
            "### Agent",
            "",
            f"对应名称：{record.agent_name.strip()}",
            "输出：",
            output,
        ],
    )


def format_agent_outputs(records: Iterable[AgentOutputRecord]) -> str:
    """Format backend agent outputs for the AGENT_INFO anchor block."""

    normalized = [
        AgentOutputRecord(record.agent_name.strip(), record.output.strip())
        for record in records
        if record.agent_name.strip()
    ]
    if not normalized:
        return "\n".join(["### Agent", "", "对应名称：", "输出："])
    return "\n\n".join(_format_agent_output(record) for record in normalized)


def update_memory_template(
    *,
    template_path: str | Path | None = None,
    task_goal: str | None = None,
    task_status: str | None = None,
    key_info_summary: str | None = None,
    agent_outputs: Iterable[AgentOutputRecord] | None = None,
    tool_call_total: int | None = None,
) -> str:
    """Update the context markdown template and return the new content."""

    path = Path(template_path) if template_path is not None else DEFAULT_TEMPLATE_PATH
    content = _read_template(path)

    content = _replace_line_value(content, "- 任务目标：", task_goal)
    content = _replace_line_value(content, "- 任务状态：", task_status)
    content = _replace_line_value(content, "- 关键信息摘要:", key_info_summary)

    if agent_outputs is not None:
        content = _replace_between_anchors(
            content,
            AGENT_INFO_START,
            AGENT_INFO_END,
            format_agent_outputs(agent_outputs),
        )

    content = _replace_line_value(content, "- 工具调用总数: ", tool_call_total)
    _write_template(path, content)
    return content


def create_session_memory_template(
    *,
    template_path: str | Path | None = None,
    dest_path: str | Path,
    task_goal: str | None = None,
    task_status: str | None = None,
    key_info_summary: str | None = None,
) -> Path:
    """Clone the canonical template into a per-small-session markdown file.

    Only invoked the first time a small session boots; later turns within the
    same small session call :func:`update_memory_template` against the same
    ``dest_path`` so the file is updated in-place instead of recreated.
    """

    source = Path(template_path) if template_path is not None else DEFAULT_TEMPLATE_PATH
    target = Path(dest_path)
    if target.exists():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

    if task_goal is not None or task_status is not None or key_info_summary is not None:
        update_memory_template(
            template_path=target,
            task_goal=task_goal,
            task_status=task_status,
            key_info_summary=key_info_summary,
        )
    return target
