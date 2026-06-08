from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional


DEFAULT_TOOL_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompt" / "tool_prompt"


class AgentRuntimeRegistry:
    """Track runtime agent identities and the tools exposed to each agent."""

    def __init__(self, tool_prompt_dir: Optional[Path] = None) -> None:
        self.tool_prompt_dir = Path(tool_prompt_dir or DEFAULT_TOOL_PROMPT_DIR)
        self._agent_ids_by_name: Dict[str, str] = {}
        self._agent_names_by_id: Dict[str, str] = {}
        self._tool_names_by_agent_id: Dict[str, List[str]] = {}
        self._tool_prompts = self._load_tool_prompts()

    def register_agent(self, agent_name: str, tool_names: Iterable[str]) -> str:
        name = str(agent_name or "").strip()
        if not name:
            raise ValueError("agent_name is required")

        agent_id = self._agent_ids_by_name.get(name)
        if agent_id is None:
            agent_id = f"agent-{len(self._agent_ids_by_name) + 1:04d}"
            self._agent_ids_by_name[name] = agent_id
            self._agent_names_by_id[agent_id] = name

        self._tool_names_by_agent_id[agent_id] = self._normalize_tool_names(tool_names)
        return agent_id

    def agent_name(self, agent_id: Optional[str]) -> Optional[str]:
        if not agent_id:
            return None
        return self._agent_names_by_id.get(str(agent_id).strip())

    def tool_names_for_agent(self, agent_id: Optional[str]) -> List[str]:
        if not agent_id:
            return []
        return list(self._tool_names_by_agent_id.get(str(agent_id).strip(), []))

    def has_tool_for_agent(self, agent_id: Optional[str], tool_name: str) -> bool:
        return str(tool_name or "").strip() in set(self.tool_names_for_agent(agent_id))

    def tool_prompt(self, tool_name: str) -> str:
        return self._tool_prompts.get(str(tool_name or "").strip(), "")

    def managed_tool_names(self) -> List[str]:
        return sorted(self._tool_prompts)

    def _normalize_tool_names(self, tool_names: Iterable[str]) -> List[str]:
        managed = set(self.managed_tool_names())
        normalized: List[str] = []
        seen = set()
        for raw_name in tool_names or []:
            name = str(raw_name or "").strip()
            if not name or name in seen or name not in managed:
                continue
            seen.add(name)
            normalized.append(name)
        return normalized

    def _load_tool_prompts(self) -> Dict[str, str]:
        prompts: Dict[str, str] = {}
        if not self.tool_prompt_dir.exists():
            return prompts
        for path in sorted(self.tool_prompt_dir.glob("*.md")):
            tool_name = path.stem.strip()
            if not tool_name or tool_name == "tool_call":
                continue
            prompts[tool_name] = path.read_text(encoding="utf-8").strip()
        return prompts
