from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.local_executor import ExecutorProtocol, LocalWorkspaceExecutor
from project_template.project_templete import (
    PROJECT_ROOT_DIRS,
    RUNTIME_PROJECT_DIRS,
    RUNTIME_PROJECT_FILES,
)
from run_time_templete.creat_runtime import runtime_files



def create_project(project_name: str, executor: ExecutorProtocol | None = None) -> str:
    name = project_name.strip().replace(" ", "_")
    if not name:
        print("project_name cannot be empty", file=sys.stderr)
        sys.exit(1)

    exec_ = executor or LocalWorkspaceExecutor(PROJECT_ROOT / "workspace")
    base = f"/workspace/{name}"
    runtime_base = f"{base}/runtime"

    for directory in PROJECT_ROOT_DIRS:
        path = f"{base}/{directory}"
        exec_.run(["mkdir", "-p", path])

    for directory in RUNTIME_PROJECT_DIRS:
        path = f"{runtime_base}/{directory}"
        exec_.run(["mkdir", "-p", path])

    for rel_path, content in {**RUNTIME_PROJECT_FILES, **runtime_files()}.items():
        container_path = f"{runtime_base}/{rel_path}"
        check = exec_.run(["test", "-f", container_path])
        if check.returncode == 0:
            continue
        result = exec_.write_file(container_path, content)
        if not result.ok:
            print(f"failed to write: {container_path}\n{result.stderr}", file=sys.stderr)

    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a runnable agent project scaffold.")
    parser.add_argument("project_name", help="Project name")
    args = parser.parse_args()
    create_project(args.project_name)


if __name__ == "__main__":
    main()
