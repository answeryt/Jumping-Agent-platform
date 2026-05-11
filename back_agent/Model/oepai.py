from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI

from config.settings import LLMConfig, load_settings
from Model.base_model import BaseModel

class OpenAIModel(BaseModel):
    """OpenAI 模型接口类"""
    
    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        verbose: bool = True,
        default_stream: Optional[bool] = None,
    ):
        llm_config = config or load_settings().llm_default

        self.target_model = llm_config.model
        self.default_temperature = float(llm_config.temperature)
        self.default_max_tokens = llm_config.max_tokens

        if llm_config.base_url:
            self.client = OpenAI(api_key=llm_config.api_key, base_url=llm_config.base_url)
        else:
            self.client = OpenAI(api_key=llm_config.api_key)
        self.verbose = verbose
        if default_stream is None:
            self.default_stream = bool(llm_config.stream)
        else:
            self.default_stream = bool(default_stream)

    def set_stream_mode(self, stream: bool) -> None:
        """Set default stream mode for all model calls."""
        self.default_stream = bool(stream)

    @staticmethod
    def _clip(value: Any, limit: int = 1200) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        return f"{text[:limit]} ...[truncated]"

    def _log(self, content: str) -> None:
        if self.verbose:
            print(content, flush=True)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: Optional[bool] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """调用 OpenAI API，支持流式输出并打印完整调用日志"""
        try:
            effective_temperature = self.default_temperature if temperature is None else float(temperature)
            effective_max_tokens = self.default_max_tokens if max_tokens is None else max_tokens
            effective_stream = self.default_stream if stream is None else bool(stream)
            self._log("\n[Model] 发起模型调用")
            self._log(
                f"[Model] model={self.target_model}, temperature={effective_temperature}, stream={effective_stream}"
            )
            response = self.client.chat.completions.create(
                model=self.target_model,
                messages=messages,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                stream=effective_stream,
                **kwargs
            )

            if not effective_stream:
                message = response.choices[0].message
                content = message.content or ""
                self._log("[Model] 推理输出:")
                print(content, flush=True)
                return {"content": content}

            full_response = ""
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content is not None:
                    content = delta.content
                    full_response += content
                    print(content, end="", flush=True)

            print()
            return {"content": full_response}
                
        except Exception as e:
            raise Exception(f"调用 OpenAI API 失败: {str(e)}")
    
    def chat_with_system(
        self,
        system_message: str,
        user_message: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """使用系统提示词和用户消息调用 API"""
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        return self.chat(messages, temperature, max_tokens, **kwargs)
    
    def get_model_name(self) -> str:
        """获取当前使用的模型名称"""
        return self.target_model
