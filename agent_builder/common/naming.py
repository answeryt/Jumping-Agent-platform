from __future__ import annotations

import re


def normalize_python_name(name: str, default_prefix: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower().replace("-", "_"))
    normalized = re.sub(r"_+", "_", raw).strip("_")
    if not normalized:
        normalized = default_prefix
    if normalized[0].isdigit():
        normalized = f"{default_prefix}_{normalized}"
    return normalized


def to_class_prefix(name: str, default_prefix: str) -> str:
    safe_name = normalize_python_name(name, default_prefix)
    parts = [part for part in safe_name.split("_") if part]
    return "".join(part.capitalize() for part in parts) or default_prefix.capitalize()
