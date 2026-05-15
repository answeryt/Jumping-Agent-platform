# -*- coding: utf-8 -*-
"""Tests for backend memory markdown template writer."""

from __future__ import annotations

from pathlib import Path

from memory_template_writer import AgentOutputRecord, update_memory_template


_TEMPLATE = """# 上下文表单

<!-- TASK_OVERVIEW_START -->
## 任务概览

- 任务目标：
- 任务状态：
- 关键信息摘要:
<!-- TASK_OVERVIEW_END -->

---

<!-- AGENT_INFO_START -->
### Agent

对应名称：
输出：
<!-- AGENT_INFO_END -->
---

<!-- TOOL_USAGE_START -->
- 工具调用总数: 
<!-- TOOL_USAGE_END -->
"""


def test_update_memory_template_writes_overview_agent_outputs_and_tool_count(
    tmp_path: Path,
) -> None:
    template_path = tmp_path / "memory_templete.md"
    template_path.write_text(_TEMPLATE, encoding="utf-8")

    content = update_memory_template(
        template_path=template_path,
        task_goal="构建测试 Agent",
        task_status="已完成",
        key_info_summary="完成 2 个 Agent 输出回写",
        agent_outputs=[
            AgentOutputRecord("planner", "生成计划"),
            AgentOutputRecord("coder", "生成代码"),
        ],
        tool_call_total=2,
    )

    assert "- 任务目标：构建测试 Agent" in content
    assert "- 任务状态：已完成" in content
    assert "- 关键信息摘要:完成 2 个 Agent 输出回写" in content
    assert "对应名称：planner" in content
    assert "输出：\n生成计划" in content
    assert "对应名称：coder" in content
    assert "- 工具调用总数: 2" in content
