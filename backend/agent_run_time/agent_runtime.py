from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backend.agent_manager import AgentIdStore
from backend.agent_run_time.prompt_runtime import ToolPromptRegistry


class AgentRuntimeRegistry:
    """Track runtime agent identities and the tools exposed to each agent."""

    def __init__(
        self,
        tool_prompt_dir: Optional[Path] = None,
        tool_prompt_registry: Optional[ToolPromptRegistry] = None,
        agent_id_store: Optional[AgentIdStore] = None,
    ) -> None:
        self.tool_prompt_registry = tool_prompt_registry or ToolPromptRegistry(tool_prompt_dir)
        self.agent_id_store = agent_id_store or AgentIdStore()
        self._agent_ids_by_name: Dict[str, str] = {}
        self._agent_names_by_id: Dict[str, str] = {}
        self._tool_names_by_agent_id: Dict[str, List[str]] = {}

    def register_agent(self, agent_name: str, tool_names: Iterable[str]) -> str:
        name = str(agent_name or "").strip()
        if not name:
            raise ValueError("agent_name is required")

        agent_id = self._agent_ids_by_name.get(name)
        if agent_id is None:
            agent_id = self.agent_id_store.get_or_create_agent_id(name)
        self._agent_ids_by_name[name] = agent_id
        self._agent_names_by_id[agent_id] = name

        self._tool_names_by_agent_id[agent_id] = self._normalize_tool_names(tool_names)
        return agent_id

    def agent_name(self, agent_id: Optional[str]) -> Optional[str]:
        if not agent_id:
            return None
        value = str(agent_id).strip()
        return self._agent_names_by_id.get(value) or self.agent_id_store.agent_name(value)

    def persisted_agents(self) -> List[Dict[str, Any]]:
        return self.agent_id_store.list_agents()

    def tool_names_for_agent(self, agent_id: Optional[str]) -> List[str]:
        if not agent_id:
            return []
        return list(self._tool_names_by_agent_id.get(str(agent_id).strip(), []))

    def has_tool_for_agent(self, agent_id: Optional[str], tool_name: str) -> bool:
        return str(tool_name or "").strip() in set(self.tool_names_for_agent(agent_id))

    def tool_prompt(self, tool_name: str) -> str:
        return self.tool_prompt_registry.tool_prompt(tool_name)

    def tool_call_prompt(self) -> str:
        return self.tool_prompt_registry.tool_call_prompt()

    def tool_system_prompt(self) -> str:
        return self.tool_prompt_registry.tool_system_prompt()

    def managed_tool_names(self) -> List[str]:
        return self.tool_prompt_registry.managed_tool_names()

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
