from __future__ import annotations

import re


def normalize_python_name(name: str, default_prefix: str) -> str:
    # 所有由用户输入生成的文件名、类名、agent key 都先走这里，避免生成非法 Python 标识符。
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower().replace("-", "_"))
    normalized = re.sub(r"_+", "_", raw).strip("_")
    if not normalized:
        normalized = default_prefix
    if normalized[0].isdigit():
        normalized = f"{default_prefix}_{normalized}"
    return normalized


def to_class_prefix(name: str, default_prefix: str) -> str:
    # 文件名使用 snake_case，类名前缀使用 PascalCase，两者都从同一套安全命名规则派生。
    safe_name = normalize_python_name(name, default_prefix)
    parts = [part for part in safe_name.split("_") if part]
    return "".join(part.capitalize() for part in parts) or default_prefix.capitalize()
