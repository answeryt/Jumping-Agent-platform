from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional


DEFAULT_TOOL_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompt" / "tool_prompt"
DEFAULT_TOOL_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompt" / "system_prompt" / "system_prompt.md"
DEFAULT_MEMORY_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "memory" / "memory_templete.md"


class RuntimePromptLoader:
    """Load generated workspace agent prompts.

    Generated agents keep depending on a small ``load(filename, agent_type)``
    contract, while the concrete file loading lives in backend runtime code.
    """

    def __init__(self, prompt_dir: Optional[Path] = None) -> None:
        self.prompt_dir = Path(prompt_dir) if prompt_dir is not None else Path(__file__).resolve().parents[1] / "Prompt"
        self.runtime_root = self.prompt_dir.parent.resolve()

    def load_agent_prompt(self, filename: str, agent_type: Optional[str] = None) -> str:
        del agent_type
        path = self.prompt_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8").strip()

    def load(self, filename: str, agent_type: Optional[str] = None) -> str:
        return self.load_agent_prompt(filename, agent_type)


class ToolPromptRegistry:
    """Load backend tool prompts from the central tool prompt directory."""

    def __init__(
        self,
        tool_prompt_dir: Optional[Path] = None,
        tool_system_prompt_path: Optional[Path] = None,
        memory_template_path: Optional[Path] = None,
    ) -> None:
        self.tool_prompt_dir = Path(tool_prompt_dir or DEFAULT_TOOL_PROMPT_DIR)
        self.tool_system_prompt_path = Path(tool_system_prompt_path or DEFAULT_TOOL_SYSTEM_PROMPT_PATH)
        self.memory_template_path = Path(memory_template_path or DEFAULT_MEMORY_TEMPLATE_PATH)
        self._tool_prompts = self._load_tool_prompts()
        self._tool_call_prompt = self._load_tool_call_prompt()
        self._tool_system_prompt = self._load_tool_system_prompt()

    def tool_prompt(self, tool_name: str) -> str:
        return self._tool_prompts.get(str(tool_name or "").strip(), "")

    def tool_call_prompt(self) -> str:
        return self._tool_call_prompt

    def tool_system_prompt(self) -> str:
        return self._tool_system_prompt

    def managed_tool_names(self) -> list[str]:
        return sorted(self._tool_prompts)

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

    def _load_tool_call_prompt(self) -> str:
        path = self.tool_prompt_dir / "tool_call.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _load_tool_system_prompt(self) -> str:
        if self.tool_system_prompt_path.exists():
            return self.tool_system_prompt_path.read_text(encoding="utf-8").strip()
        if not self.memory_template_path.exists():
            return ""
        text = self.memory_template_path.read_text(encoding="utf-8")
        return self._extract_marked_block(
            text,
            "<!-- SYSTEM_PROMPT_START -->",
            "<!-- SYSTEM_PROMPT_END -->",
        ).strip()

    @staticmethod
    def _extract_marked_block(text: str, start_marker: str, end_marker: str) -> str:
        start = text.find(start_marker)
        if start < 0:
            return ""
        start += len(start_marker)
        end = text.find(end_marker, start)
        if end < 0:
            return ""
        return text[start:end]
