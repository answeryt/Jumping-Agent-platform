from __future__ import annotations

from typing import Any, Dict, Optional

from Config.settings import LLMConfig, load_settings
from Model.base_model import BaseModel

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


class OpenAIModel(BaseModel):
    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        llm_config = config or load_settings().llm_default
        self.model_name = llm_config.model
        self.temperature = llm_config.temperature
        self.max_tokens = llm_config.max_tokens
        self.stream = llm_config.stream
        self.base_url = llm_config.base_url
        self.api_key = llm_config.api_key

    def _build_client(self):
        if OpenAI is None:
            raise RuntimeError("openai package is required to run generated projects")
        if not self.api_key:
            raise RuntimeError("Configured api_key is required")
        if self.base_url:
            return OpenAI(api_key=self.api_key, base_url=self.base_url)
        return OpenAI(api_key=self.api_key)

    def chat_with_system(self, system_message: str, user_message: str, **kwargs: Any) -> Dict[str, Any]:
        client = self._build_client()
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            stream=bool(kwargs.get("stream", self.stream)),
        )

        if bool(kwargs.get("stream", self.stream)):
            full_text = ""
            for chunk in response:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    full_text += content
            return {"content": full_text}

        message = response.choices[0].message
        text = message.content or ""
        return {"content": text}

    def get_model_name(self) -> str:
        return self.model_name
