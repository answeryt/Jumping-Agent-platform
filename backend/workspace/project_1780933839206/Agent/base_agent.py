from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


for _parent in Path(__file__).resolve().parents:
    if (_parent / "backend" / "agent_run_time" / "prompt_runtime.py").exists():
        sys.path.insert(0, str(_parent))
        break

from backend.agent_run_time.prompt_runtime import RuntimePromptLoader as PromptLoader


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
        self.prompt_loader = prompt_loader or PromptLoader(
            prompt_dir=Path(__file__).resolve().parents[1] / "Prompt"
        )

    def load_prompt(self) -> str:
        if self.config is None or not getattr(self.config, "prompt_file", ""):
            raise ValueError("Agent config.prompt_file is required")
        return self.prompt_loader.load(self.config.prompt_file, self.agent_type)

    @abstractmethod
    def run(self, user_input: str, **kwargs: Any) -> str:
        raise NotImplementedError
