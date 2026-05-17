from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skill.skill_registry import get_skill


def test_common_agent_skill_emphasizes_user_oriented_prompt_quality() -> None:
    skill = get_skill("common-agent-skill")
    content = skill.content

    assert "用户价值优先于模板完整" in content
    assert "默认不要要求 agent 暴露内部推理过程" in content
    assert "Prompt 质量自检" in content
    assert "减少模板化输出" in content


def test_common_agent_skill_discourages_internal_only_fields_by_default() -> None:
    skill = get_skill("common-agent-skill")
    content = skill.content

    assert "默认不要要求输出 `skills_used`、`thoughts`、`reasoning_steps` 一类内部字段" in content
    assert "只有在工作区契约明确要求结构化字段时" in content
    assert "不要为了“看起来结构化”而强行加入对用户无价值的字段" in content


def test_common_agent_skill_requires_framework_contract_identification() -> None:
    skill = get_skill("common-agent-skill")
    content = skill.content

    assert "先识别当前 agent framework contract" in content
    assert "在修改文件前，通常值得先确认当前工作区把什么视为“合法 agent”" in content
    assert "不要把某一种 agent 框架的默认写法，直接套用到另一种框架上" in content
    assert "agent 是如何被发现的：目录扫描、注册表、工厂函数、装饰器、配置文件、workflow 节点" in content


def test_multi_agent_skill_guides_workspace_level_runtime_readiness() -> None:
    skill = get_skill("multi-agent-skill")
    content = skill.content

    assert "共享 contract 与 runtime 观察" in content
    assert "检查与收尾" in content
    assert "如果运行时会自动发现多个 agent，那么“当前节点已补全”有时还不足以代表“当前 workspace 已可运行”" in content
    assert "把这些节点补到最小可运行状态，通常比只完成当前目标节点更贴近多 agent 工作区的真实交付标准" in content


def test_multi_agent_skill_keeps_guidance_generic_and_advisory() -> None:
    skill = get_skill("multi-agent-skill")
    content = skill.content

    assert "最低接入契约的思考方式" in content
    assert "最低接入契约不一定长得一样" in content
    assert "例如 `run()`、`execute()`、`invoke()`、`__call__()`、异步方法" in content
    assert "通常值得" in content or "往往更适合" in content


def test_single_agent_skill_emphasizes_direct_user_answering() -> None:
    skill = get_skill("single-agent-skill")
    content = skill.content

    assert "默认将当前 agent 视为直接面向用户的回答者" in content
    assert "默认不要要求输出 `next_agent`、`next_task`、`handoff` 等路由字段" in content
    assert "先回答可回答的部分，再补充边界、假设或必要追问" in content
