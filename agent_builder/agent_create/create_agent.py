"""
create_agent.py

用法：
    python agent_builder/agent_create/create_agent.py <agent_name>
    python agent_builder/agent_create/create_agent.py researcher
    python agent_builder/agent_create/create_agent.py data_analyst

会自动生成（写入沙盒容器 /workspace/）：
    Agent/<agent_name>_agent.py
    Prompt/<agent_name>_agent.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_template.agent_templete import agent_py, prompt_md

SANDBOX_ROOT = PROJECT_ROOT / "sandbox"
sys.path.insert(0, str(SANDBOX_ROOT))
from sandbox_executor import SandboxExecutor  # type: ignore


def to_class_prefix(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def create_agent(agent_name: str, executor: SandboxExecutor | None = None) -> None:
    name = agent_name.strip().lower().replace("-", "_")
    if not name:
        print("错误：agent_name 不能为空", file=sys.stderr)
        sys.exit(1)

    exec_ = executor or SandboxExecutor()
    class_prefix = to_class_prefix(name)
    prompt_file = f"{name}_agent.md"

    agent_container_path = f"/workspace/Agent/{name}_agent.py"
    prompt_container_path = f"/workspace/Prompt/{prompt_file}"

    # 写入 Agent 文件
    check = exec_.run(["test", "-f", agent_container_path])
    if check.returncode == 0:
        print(f"已存在，跳过：{agent_container_path}")
    else:
        result = exec_.write_file(agent_container_path, agent_py(class_prefix, name, prompt_file))
        if result.ok:
            print(f"已生成：{agent_container_path}")
        else:
            print(f"写入失败：{agent_container_path}\n{result.stderr}", file=sys.stderr)

    # 写入 Prompt 文件
    check = exec_.run(["test", "-f", prompt_container_path])
    if check.returncode == 0:
        print(f"已存在，跳过：{prompt_container_path}")
    else:
        result = exec_.write_file(prompt_container_path, prompt_md(class_prefix, name))
        if result.ok:
            print(f"已生成：{prompt_container_path}")
        else:
            print(f"写入失败：{prompt_container_path}\n{result.stderr}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="自动生成 Agent代码文件和 Prompt 骨架（写入沙盒容器）")
    parser.add_argument("agent_name", help="agent 名称，例如 researcher 或 data_analyst")
    args = parser.parse_args()
    create_agent(args.agent_name)


if __name__ == "__main__":
    main()