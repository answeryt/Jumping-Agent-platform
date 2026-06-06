from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from ..skill.skill_registry import Skill, get_skill, list_skills
except ImportError:  # pragma: no cover - legacy top-level imports
    from skill.skill_registry import Skill, get_skill, list_skills


_SKILL_SELECT_PATTERN = re.compile(r"\[SELECT_SKILL\](.*?)\[/SELECT_SKILL\]", re.IGNORECASE | re.DOTALL)

_DEFAULT_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt"
_TOOL_PROMPT_FILENAME = "tool_prompt.md"


@dataclass(frozen=True)
class SkillMetadata:
    """面向 ReactAgent 的 skill 顶层元数据。"""

    name: str
    description: str
    source: str


@dataclass(frozen=True)
class SkillDisclosure:
    """一次 skill 披露结果。"""

    selected: List[str]
    content_by_name: Dict[str, str]


class ReactAgentSkillContextManager:
    """
    ReactAgent skill 渐进式披露管理器，同时负责加载工具提示词。

    工作流：
    1. 首次调用 `build_initial_metadata_context()`，只给 agent skill metadata。
    2. agent 用 [SELECT_SKILL]skill_name[/SELECT_SKILL] 声明需要的 skill。
    3. 调用 `disclose_from_agent_reply()`，返回被选 skill 的完整正文（去除 front matter）。
    4. 调用 `enrich_system_prompt(base_prompt)` 将 tool_prompt.md 追加到 system prompt。
    """

    def __init__(self, prompt_dir: Optional[Path] = None) -> None:
        self._metadata_cache: Optional[List[SkillMetadata]] = None
        self._disclosed_skills: Set[str] = set()
        self._prompt_dir: Path = Path(prompt_dir) if prompt_dir else _DEFAULT_PROMPT_DIR
        self._tool_prompt_cache: Optional[str] = None

    def reset_runtime_state(self) -> None:
        """重置单次请求相关的披露状态，避免跨请求残留。"""
        # _metadata_cache 可以跨请求复用，但 _disclosed_skills 必须每次清空。
        self._disclosed_skills.clear()

    def load_metadata(self, force_reload: bool = False) -> List[SkillMetadata]:
        """
        加载 skill 顶层元数据。

        注意：这里仅读取 name/description/source，不暴露完整正文。
        """
        if self._metadata_cache is not None and not force_reload:
            return self._metadata_cache

        metadata_list: List[SkillMetadata] = []
        for skill in list_skills():
            metadata_list.append(
                SkillMetadata(
                    name=skill.name,
                    description=skill.description or "暂无描述",
                    source=skill.path.name,
                )
            )

        self._metadata_cache = sorted(metadata_list, key=lambda x: x.name.lower())
        return self._metadata_cache

    def build_initial_metadata_context(self) -> str:
        """构建首次注入给 ReactAgent 的 metadata 上下文。"""
        skills = self.load_metadata()
        if not skills:
            return "当前没有可用 skill。"

        lines: List[str] = [
            "你当前可用的 skill 仅展示 metadata（名称/描述/来源）：",
            "如果你需要某个 skill 的完整正文，请在回复中显式使用标签：",
            "[SELECT_SKILL]skill_name[/SELECT_SKILL]",
            "",
            "可用 skills:",
        ]
        for item in skills:
            lines.append(f"- name: {item.name} | description: {item.description} | source: {item.source}")
        return "\n".join(lines)

    def disclose_from_agent_reply(self, agent_reply: str) -> SkillDisclosure:
        """
        从 agent 回复中提取 skill 选择，并返回对应 skill 的完整正文（不重复下发）。

        支持在一条回复中选择多个 skill：
        [SELECT_SKILL]a[/SELECT_SKILL] ... [SELECT_SKILL]b[/SELECT_SKILL]
        """
        # agent 回复里的 SELECT_SKILL 标签是唯一触发 skill 正文披露的协议。
        requested = self.extract_selected_skill_names(agent_reply)
        newly_selected: List[str] = []
        content_by_name: Dict[str, str] = {}

        for skill_name in requested:
            lookup_key = skill_name.strip().lower()
            if not lookup_key:
                continue

            skill = get_skill(skill_name)
            canonical_key = skill.name.strip().lower()
            if canonical_key in self._disclosed_skills:
                continue

            content_by_name[skill.name] = self._skill_body(skill)
            self._disclosed_skills.add(canonical_key)
            newly_selected.append(skill.name)

        return SkillDisclosure(selected=newly_selected, content_by_name=content_by_name)

    def build_disclosure_context(self, disclosure: SkillDisclosure) -> str:
        """将披露结果格式化为可直接注入给 ReactAgent 的上下文文本。"""
        if not disclosure.selected:
            return ""

        sections: List[str] = ["以下是你选择的 skill 完整内容："]
        for skill_name in disclosure.selected:
            body = disclosure.content_by_name[skill_name]
            sections.append(f"## Skill: {skill_name}\n\n{body}")
        return "\n\n".join(sections)

    def get_disclosed_skills(self) -> List[str]:
        """获取当前已经披露过正文的 skill 名称（小写键）。"""
        return sorted(self._disclosed_skills)

    # ------------------------------------------------------------------
    # 工具提示词注入
    # ------------------------------------------------------------------

    def load_tool_prompt(self, force_reload: bool = False) -> str:
        """
        加载 tool_prompt.md 的内容。

        文件不存在时返回空字符串（不抛异常，保证向后兼容）。
        """
        if self._tool_prompt_cache is not None and not force_reload:
            return self._tool_prompt_cache

        tool_prompt_path = self._prompt_dir / _TOOL_PROMPT_FILENAME
        if tool_prompt_path.exists():
            self._tool_prompt_cache = tool_prompt_path.read_text(encoding="utf-8").strip()
        else:
            self._tool_prompt_cache = ""

        return self._tool_prompt_cache

    def enrich_system_prompt(self, base_prompt: str) -> str:
        """
        将 tool_prompt.md 追加到 base_prompt（通常为 react_agent_prompt.md 内容）。

        若 tool_prompt.md 为空或不存在，原样返回 base_prompt。
        """
        # tool_prompt 直接拼到 system prompt，使工具调用格式对所有任务都可见。
        tool_section = self.load_tool_prompt()
        if not tool_section:
            return base_prompt
        return f"{base_prompt.rstrip()}\n\n{tool_section}"

    @staticmethod
    def extract_selected_skill_names(agent_reply: str) -> List[str]:
        """解析 [SELECT_SKILL]...[/SELECT_SKILL] 标签中的技能名。"""
        picked: List[str] = []
        for item in _SKILL_SELECT_PATTERN.findall(agent_reply or ""):
            name = item.strip()
            if name:
                picked.append(name)
        return picked

    @staticmethod
    def _skill_body(skill: Skill) -> str:
        """
        返回 skill 正文（剥离顶层 front matter）。

        metadata 已在首轮提供，这里下发剩余正文即可。
        """
        _meta, body = _parse_front_matter(skill.content)
        return body or skill.content


def _parse_front_matter(content: str) -> Tuple[Dict[str, str], str]:
    """解析 markdown 顶层 front matter（简化实现）。"""
    text = (content or "").lstrip()
    if not text.startswith("---"):
        return {}, content

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content

    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx == -1:
        return {}, content

    metadata: Dict[str, str] = {}
    for raw in lines[1:end_idx]:
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")

    body = "\n".join(lines[end_idx + 1 :]).strip()
    return metadata, body


def build_reactagent_initial_skill_context() -> str:
    """便捷函数：构建 ReactAgent 首次 skill metadata 上下文。"""
    manager = ReactAgentSkillContextManager()
    return manager.build_initial_metadata_context()


def disclose_skill_content_for_reactagent(agent_reply: str) -> SkillDisclosure:
    """
    便捷函数：从 ReactAgent 回复中解析 skill 选择并返回正文披露结果。

    适合无状态调用；如需跨轮次“避免重复披露”，请复用同一个 manager 实例。
    """
    manager = ReactAgentSkillContextManager()
    return manager.disclose_from_agent_reply(agent_reply)
