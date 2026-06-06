from __future__ import annotations

import argparse
import sys
from pathlib import Path

AGENT_BUILDER_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = AGENT_BUILDER_ROOT.parent

for import_root in (PROJECT_ROOT, AGENT_BUILDER_ROOT):
    import_root_str = str(import_root)
    if import_root_str not in sys.path:
        sys.path.insert(0, import_root_str)

from agent_builder.config_template.config_templete import model_config_toml

SANDBOX_ROOT = PROJECT_ROOT / "sandbox"
if str(SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ROOT))
from sandbox_executor import SandboxExecutor  # type: ignore


def _normalize_project_name(project_name: str) -> str:
    return project_name.strip().replace(" ", "_")


def create_config(project_name: str, executor: SandboxExecutor | None = None) -> None:
    name = _normalize_project_name(project_name)
    if not name:
        print("project_name cannot be empty", file=sys.stderr)
        sys.exit(1)

    exec_ = executor or SandboxExecutor()
    model_path = f"/workspace/{name}/runtime/Config/model_config.toml"

    check = exec_.run(["test", "-f", model_path])
    if check.returncode == 0:
        print(f"exists, skipped: {model_path}")
        return

    result = exec_.write_file(model_path, model_config_toml())
    if result.ok:
        print(f"generated: {model_path}")
    else:
        print(f"failed to write: {model_path}\n{result.stderr}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Config/model_config.toml in an existing generated runtime."
    )
    parser.add_argument("project_name", help="Project name, for example my_agent")
    args = parser.parse_args()
    create_config(args.project_name)


if __name__ == "__main__":
    main()
