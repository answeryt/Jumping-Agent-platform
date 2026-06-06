from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SUPPORTED_SKILL_EXTENSIONS = {".md", ".txt"}


@dataclass(frozen=True)
class Skill:
    """Skill 结构定义。"""

    name: str
    path: Path
    content: str
    description: str = ""


class SkillContentParser:
    """负责解析 skill 文本和 front matter。"""

    @staticmethod
    def parse_front_matter(content: str) -> tuple[Dict[str, str], str]:
        stripped = content.lstrip()
        if not stripped.startswith("---"):
            return {}, content

        lines = stripped.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}, content

        end_idx = -1
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                end_idx = idx
                break
        if end_idx == -1:
            return {}, content

        meta: Dict[str, str] = {}
        for raw in lines[1:end_idx]:
            line = raw.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"').strip("'")

        body = "\n".join(lines[end_idx + 1 :]).strip()
        return meta, body


class SkillFileDiscovery:
    """负责发现 skill 文件。"""

    def __init__(self, skill_dir: Path) -> None:
        self.skill_dir = skill_dir.resolve()

    def iter_skill_files(self) -> Iterable[Path]:
        # skill 只从 md/txt 读取，Python 管理文件不作为可披露 skill。
        for path in self.skill_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name in {"__init__.py", "skill_selection.py", "skill_registry.py"}:
                continue
            if path.suffix.lower() not in SUPPORTED_SKILL_EXTENSIONS:
                continue
            yield path


class SkillRegistry:
    """注册并读取 skill 文件内容的统一入口。"""

    def __init__(self, skill_dir: Optional[Path] = None) -> None:
        self.skill_dir = (skill_dir or Path(__file__).resolve().parent).resolve()
        self._skills_by_name: Dict[str, Skill] = {}
        self._loaded = False
        self._discovery = SkillFileDiscovery(self.skill_dir)
        self._parser = SkillContentParser()

    def load(self, force_reload: bool = False) -> Dict[str, Skill]:
        # 注册表按多个 alias 建索引，模型用文件名或 front matter name 都能命中。
        if self._loaded and not force_reload:
            return self._skills_by_name

        skills: Dict[str, Skill] = {}
        for file_path in self._discovery.iter_skill_files():
            content = file_path.read_text(encoding="utf-8").strip()
            if not content:
                continue

            metadata, _body = self._parser.parse_front_matter(content)
            skill_name = (
                str(metadata.get("name", "")).strip()
                or file_path.stem
                or str(file_path.relative_to(self.skill_dir))
            )
            description = str(metadata.get("description", "")).strip()
            skill = Skill(name=skill_name, path=file_path, content=content, description=description)

            for key in self._build_aliases(skill):
                skills[key] = skill

        self._skills_by_name = skills
        self._loaded = True
        return self._skills_by_name

    def list_skills(self) -> List[Skill]:
        self.load()
        unique: Dict[Path, Skill] = {}
        for skill in self._skills_by_name.values():
            unique[skill.path] = skill
        return sorted(unique.values(), key=lambda s: s.name.lower())

    def get_skill(self, name: str) -> Skill:
        self.load()
        key = name.strip().lower()
        skill = self._skills_by_name.get(key)
        if skill is None:
            known = ", ".join(item.name for item in self.list_skills()) or "<none>"
            raise KeyError(f"未找到 skill: {name}；可用 skill: {known}")
        return skill

    def get_skill_content(self, name: str) -> str:
        return self.get_skill(name).content

    def get_all_skill_contents(self) -> Dict[str, str]:
        return {skill.name: skill.content for skill in self.list_skills()}

    def build_skills_context(self, names: Optional[Iterable[str]] = None) -> str:
        # 这个函数用于一次性注入 skill；React workflow 默认走渐进披露，避免上下文过大。
        if names is None:
            target_skills = self.list_skills()
        else:
            target_skills = [self.get_skill(name) for name in names]

        sections: List[str] = []
        for skill in target_skills:
            header = f"## Skill: {skill.name}\nsource: {skill.path.name}"
            sections.append(f"{header}\n\n{skill.content}")
        return "\n\n".join(sections)

    def _build_aliases(self, skill: Skill) -> List[str]:
        relative_path = skill.path.relative_to(self.skill_dir)
        aliases = {
            skill.name.strip().lower(),
            skill.path.stem.strip().lower(),
            str(relative_path).replace("\\", "/").strip().lower(),
            relative_path.name.strip().lower(),
        }
        return [alias for alias in aliases if alias]


_DEFAULT_REGISTRY = SkillRegistry()


def load_skills(force_reload: bool = False) -> Dict[str, Skill]:
    return _DEFAULT_REGISTRY.load(force_reload=force_reload)


def list_skills() -> List[Skill]:
    return _DEFAULT_REGISTRY.list_skills()


def get_skill(name: str) -> Skill:
    return _DEFAULT_REGISTRY.get_skill(name)


def get_skill_content(name: str) -> str:
    return _DEFAULT_REGISTRY.get_skill_content(name)


def get_all_skill_contents() -> Dict[str, str]:
    return _DEFAULT_REGISTRY.get_all_skill_contents()


def build_skills_context(names: Optional[Iterable[str]] = None) -> str:
    return _DEFAULT_REGISTRY.build_skills_context(names=names)
