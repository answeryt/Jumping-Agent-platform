from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent
BACK_AGENT_ROOT = REPO_ROOT / "back_agent"
BACKEND_ROOT = REPO_ROOT / "backend"
WORKSPACE_ROOT = BACKEND_ROOT / "workspace"
DEFAULT_ENV_NAME = "OPENAI_API_KEY"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set model API keys for back_agent and generated Agent workspaces.",
    )
    parser.add_argument(
        "api_key",
        nargs="?",
        help="API key to write. Omit this to enter it securely.",
    )
    parser.add_argument(
        "--scope",
        choices=("all", "back-agent", "workspaces"),
        default="all",
        help="Where to write the key. Default: all.",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        default=[],
        help=(
            "Workspace path or name under backend/workspace. "
            "May be repeated. Defaults to all workspaces when scope includes workspaces."
        ),
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Only update the most recently modified generated workspace.",
    )
    parser.add_argument(
        "--env-name",
        default="",
        help="Override the env var name instead of reading api_key_env from model_config.toml.",
    )
    parser.add_argument(
        "--back-agent-root",
        default=str(BACK_AGENT_ROOT),
        help="Path to back_agent root. Default: ../back_agent.",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(WORKSPACE_ROOT),
        help="Path to generated workspaces root. Default: ./workspace.",
    )
    return parser.parse_args(argv)


def read_api_key(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        value = getpass.getpass("Model API Key: ").strip()
    if not value:
        raise ValueError("API Key 不能为空")
    return value


def resolve_env_name(config_path: Path, override: str = "") -> str:
    override = override.strip()
    if override:
        return override

    if config_path.exists() and tomllib is not None:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
        env_name = (
            data.get("llm", {})
            .get("default", {})
            .get("api_key_env", "")
        )
        env_name = str(env_name).strip()
        if env_name:
            return env_name

    if config_path.exists():
        match = re.search(
            r'^\s*api_key_env\s*=\s*["\']([^"\']+)["\']',
            config_path.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        if match:
            return match.group(1).strip()

    return DEFAULT_ENV_NAME


def quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def parse_dotenv_value(env_path: Path, key: str) -> str:
    if not env_path.exists():
        return ""

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value.strip()
    return ""


def upsert_dotenv(env_path: Path, key: str, value: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    next_line = f"{key}={quote_env_value(value)}"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    changed = False
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        candidate = stripped[7:].strip() if stripped.startswith("export ") else stripped
        if candidate.startswith(f"{key}="):
            output.append(next_line)
            changed = True
        else:
            output.append(line)

    if not changed:
        if output and output[-1].strip():
            output.append("")
        output.append(next_line)

    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")


def workspace_candidates(workspace_root: Path) -> list[Path]:
    if not workspace_root.exists():
        return []
    return sorted(
        (
            path
            for path in workspace_root.iterdir()
            if path.is_dir() and (path / "Config" / "model_config.toml").exists()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def resolve_workspace(path_or_name: str, workspace_root: Path) -> Path:
    candidate = Path(path_or_name).expanduser()
    if candidate.exists():
        return candidate.resolve()
    candidate = workspace_root / path_or_name
    if candidate.exists():
        return candidate.resolve()
    raise FileNotFoundError(f"找不到 workspace: {path_or_name}")


def selected_workspaces(args: argparse.Namespace) -> list[Path]:
    workspace_root = Path(args.workspace_root).expanduser().resolve()
    if args.workspace:
        workspaces = [resolve_workspace(item, workspace_root) for item in args.workspace]
    else:
        workspaces = workspace_candidates(workspace_root)

    if args.latest:
        return workspaces[:1]
    return workspaces


def update_back_agent(api_key: str, env_name_override: str, back_agent_root: Path) -> Path:
    config_path = back_agent_root / "config" / "model_config.toml"
    env_name = resolve_env_name(config_path, env_name_override)
    env_path = back_agent_root / ".env"
    upsert_dotenv(env_path, env_name, api_key)
    return env_path


def update_workspaces(api_key: str, env_name_override: str, workspaces: Iterable[Path]) -> list[Path]:
    updated: list[Path] = []
    for workspace in workspaces:
        config_path = workspace / "Config" / "model_config.toml"
        if not config_path.exists():
            print(f"[skip] {workspace} 缺少 Config/model_config.toml")
            continue
        env_name = resolve_env_name(config_path, env_name_override)
        env_path = workspace / ".env"
        upsert_dotenv(env_path, env_name, api_key)
        updated.append(env_path)
    return updated


def resolve_configured_api_key(
    env_name: str,
    *,
    back_agent_root: Path = BACK_AGENT_ROOT,
) -> str:
    """Resolve a configured key without exposing it in logs.

    Runtime generation can be triggered after `set_agent_api_key.py` has
    already stored the key in `back_agent/.env`, while the orchestrator process
    may not have that value in its own environment. Prefer the live environment
    when present, then fall back to the persisted back_agent dotenv.
    """
    value = os.getenv(env_name, "").strip()
    if value:
        return value
    return parse_dotenv_value(back_agent_root / ".env", env_name)


def auto_update_workspace_from_configured_key(
    workspace: Path,
    *,
    env_name_override: str = "",
    back_agent_root: Path = BACK_AGENT_ROOT,
) -> Path | None:
    config_path = workspace / "Config" / "model_config.toml"
    if not config_path.exists():
        return None

    env_name = resolve_env_name(config_path, env_name_override)
    api_key = resolve_configured_api_key(env_name, back_agent_root=back_agent_root)
    if not api_key:
        return None

    env_path = workspace / ".env"
    upsert_dotenv(env_path, env_name, api_key)
    return env_path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    api_key = read_api_key(args.api_key)
    touched: list[Path] = []

    if args.scope in ("all", "back-agent"):
        back_agent_root = Path(args.back_agent_root).expanduser().resolve()
        touched.append(update_back_agent(api_key, args.env_name, back_agent_root))

    if args.scope in ("all", "workspaces"):
        workspaces = selected_workspaces(args)
        if not workspaces:
            print("[warn] 没有找到已构建 Agent workspace")
        touched.extend(update_workspaces(api_key, args.env_name, workspaces))

    for path in touched:
        print(f"[ok] 已更新 {path}")
    print("完成。API Key 未输出到终端。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
