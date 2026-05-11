from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, Optional

import tomllib


@dataclass(frozen=True)
class LLMConfig:
    model: str
    api_key: str
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = True


@dataclass(frozen=True)
class AppSettings:
    llm_default: LLMConfig


_SETTINGS_CACHE: Optional[AppSettings] = None
_ENV_LOADED = False


def _config_file_path() -> Path:
    return Path(__file__).resolve().parent / "model_config.toml"


def _dotenv_file_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"


def _load_env_once() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    dotenv_path = _dotenv_file_path()
    if dotenv_path.exists():
        with dotenv_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)

    _ENV_LOADED = True


def _to_llm_config(data: Dict[str, Any]) -> LLMConfig:
    model = str(data.get("model", "")).strip()
    api_key_env = str(data.get("api_key_env", "")).strip()
    api_key = os.getenv(api_key_env, "").strip() if api_key_env else ""
    base_url_raw = data.get("base_url")
    base_url = str(base_url_raw).strip() if base_url_raw else None

    if not model:
        raise ValueError("配置缺少 llm.default.model")
    if not api_key:
        if api_key_env:
            raise ValueError(f"环境变量未设置: {api_key_env}")
        raise ValueError("配置缺少 llm.default.api_key_env")

    max_tokens_raw = data.get("max_tokens")
    max_tokens = int(max_tokens_raw) if max_tokens_raw is not None else None

    return LLMConfig(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=float(data.get("temperature", 0.7)),
        max_tokens=max_tokens,
        stream=bool(data.get("stream", True)),
    )


def load_settings(force_reload: bool = False) -> AppSettings:
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None and not force_reload:
        return _SETTINGS_CACHE

    _load_env_once()

    path = _config_file_path()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with path.open("rb") as f:
        raw = tomllib.load(f)

    llm_section = raw.get("llm", {})
    default_llm = llm_section.get("default", {})
    llm_default = _to_llm_config(default_llm)

    _SETTINGS_CACHE = AppSettings(llm_default=llm_default)
    return _SETTINGS_CACHE
