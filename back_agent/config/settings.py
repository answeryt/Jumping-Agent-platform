from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]


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


def _strip_inline_comment(value: str) -> str:
    in_quote: str | None = None
    escaped = False
    output: list[str] = []
    for char in value:
        if escaped:
            output.append(char)
            escaped = False
            continue
        if char == "\\" and in_quote:
            output.append(char)
            escaped = True
            continue
        if char in ("'", '"'):
            if in_quote == char:
                in_quote = None
            elif in_quote is None:
                in_quote = char
            output.append(char)
            continue
        if char == "#" and in_quote is None:
            break
        output.append(char)
    return "".join(output).strip()


def _parse_toml_scalar(value: str) -> Any:
    value = _strip_inline_comment(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _parse_toml_simple(content: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    current: Dict[str, Any] = result
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if not section:
                raise ValueError("Empty TOML section name")
            current = result
            for part in section.split("."):
                part = part.strip()
                if not part:
                    raise ValueError(f"Invalid TOML section: {section}")
                nested = current.setdefault(part, {})
                if not isinstance(nested, dict):
                    raise ValueError(f"TOML section conflicts with scalar: {section}")
                current = nested
            continue
        if "=" not in line:
            raise ValueError(f"Unsupported TOML line: {raw_line}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Unsupported TOML line: {raw_line}")
        current[key] = _parse_toml_scalar(raw_value.strip())
    return result


def _load_toml(path: Path) -> Dict[str, Any]:
    if tomllib is not None:
        with path.open("rb") as file:
            return tomllib.load(file)

    try:
        import tomli  # type: ignore
    except ModuleNotFoundError:
        return _parse_toml_simple(path.read_text(encoding="utf-8"))

    with path.open("rb") as file:
        return tomli.load(file)


def _config_file_path() -> Path:
    # back_agent 自己的模型配置固定放在 back_agent/config/model_config.toml。
    return Path(__file__).resolve().parent / "model_config.toml"


def _dotenv_file_path() -> Path:
    # .env 放在 back_agent 根目录，和 config 目录分开，方便部署时单独替换密钥。
    return Path(__file__).resolve().parent.parent / ".env"


def _load_env_once() -> None:
    # 只加载一次 .env，并且不覆盖进程里已经存在的环境变量。
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
    # TOML 里只保存 api_key_env，不直接保存密钥；真实 key 从环境变量读取。
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
    # 配置读取带缓存；测试或热更新时可以用 force_reload=True 强制重读。
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None and not force_reload:
        return _SETTINGS_CACHE

    _load_env_once()

    path = _config_file_path()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    raw = _load_toml(path)

    llm_section = raw.get("llm", {})
    default_llm = llm_section.get("default", {})
    llm_default = _to_llm_config(default_llm)

    _SETTINGS_CACHE = AppSettings(llm_default=llm_default)
    return _SETTINGS_CACHE
