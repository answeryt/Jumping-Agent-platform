from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class PromptLoader:
    def __init__(self, prompt_dir: Optional[Path] = None) -> None:
        self.prompt_dir = prompt_dir or Path(__file__).resolve().parents[1] / "Prompt"
        self.runtime_root = self.prompt_dir.parent.resolve()

    def load(self, filename: str, agent_type: Optional[str] = None) -> str:
        del agent_type
        path = self.prompt_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8").strip()


class BaseAgent(ABC):
    def __init__(
        self,
        agent_type: str,
        model: Any = None,
        config: Any = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        self.agent_type = agent_type
        self.model = model
        self.config = config
        self.prompt_loader = prompt_loader or PromptLoader()

    def load_prompt(self) -> str:
        if self.config is None or not getattr(self.config, "prompt_file", ""):
            raise ValueError("Agent config.prompt_file is required")
        return self.prompt_loader.load(self.config.prompt_file, self.agent_type)

    @abstractmethod
    def run(self, user_input: str, **kwargs: Any) -> str:
        raise NotImplementedError
