from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_template.agent_templete import agent_py, prompt_md
from common.naming import normalize_python_name, to_class_prefix

SANDBOX_ROOT = PROJECT_ROOT / "sandbox"
sys.path.insert(0, str(SANDBOX_ROOT))
from sandbox_executor import SandboxExecutor  # type: ignore


def create_agent(agent_name: str, executor: SandboxExecutor | None = None) -> str:
    name = normalize_python_name(agent_name, "agent")
    exec_ = executor or SandboxExecutor()
    class_prefix = to_class_prefix(name, "agent")
    prompt_file = f"{name}_agent.md"

    agent_container_path = f"/workspace/Agent/{name}_agent.py"
    prompt_container_path = f"/workspace/Prompt/{prompt_file}"

    if exec_.run(["test", "-f", agent_container_path]).returncode != 0:
        result = exec_.write_file(agent_container_path, agent_py(class_prefix, name, prompt_file))
        if not result.ok:
            print(f"failed to write: {agent_container_path}\n{result.stderr}", file=sys.stderr)

    if exec_.run(["test", "-f", prompt_container_path]).returncode != 0:
        result = exec_.write_file(prompt_container_path, prompt_md(class_prefix, name))
        if not result.ok:
            print(f"failed to write: {prompt_container_path}\n{result.stderr}", file=sys.stderr)

    return name


def main() -> None:
    parser = argparse.ArgumentParser(description="Create generated Agent and Prompt files.")
    parser.add_argument("agent_name", help="Agent name")
    args = parser.parse_args()
    create_agent(args.agent_name)


if __name__ == "__main__":
    main()
