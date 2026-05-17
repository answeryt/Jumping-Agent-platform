from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SkillSelection:
    """一次任务所需的 skill 组合。"""

    common: str
    specific: str

    @property
    def ordered_names(self) -> Tuple[str, str]:
        return (self.common, self.specific)


COMMON_AGENT_SKILL = "common-agent-skill"
SINGLE_AGENT_SKILL = "single-agent-skill"
MULTI_AGENT_SKILL = "multi-agent-skill"


def determine_agent_skill_mode(*, static_downstream: int, dynamic_downstream: int) -> str:
    """根据上下游协作形态选择 single / multi agent skill。"""
    if static_downstream > 0 or dynamic_downstream > 0:
        return MULTI_AGENT_SKILL
    return SINGLE_AGENT_SKILL


def select_agent_skills(*, static_downstream: int, dynamic_downstream: int) -> SkillSelection:
    """返回当前任务必须加载的 skill 组合。"""
    return SkillSelection(
        common=COMMON_AGENT_SKILL,
        specific=determine_agent_skill_mode(
            static_downstream=static_downstream,
            dynamic_downstream=dynamic_downstream,
        ),
    )


def build_select_skill_prefix(*skill_names: str) -> str:
    """构造 SELECT_SKILL 前缀，按顺序显式请求 skill。"""
    cleaned = [name.strip() for name in skill_names if name and name.strip()]
    return "\n".join(f"[SELECT_SKILL]{name}[/SELECT_SKILL]" for name in cleaned)


def build_agent_skill_prefix(*, static_downstream: int, dynamic_downstream: int) -> str:
    """生成 agent 补全任务需要的 skill 选择前缀。"""
    selection = select_agent_skills(
        static_downstream=static_downstream,
        dynamic_downstream=dynamic_downstream,
    )
    return build_select_skill_prefix(*selection.ordered_names)
