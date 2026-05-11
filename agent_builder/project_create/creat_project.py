"""
create_project.py

用法：
    python agent_builder/project_create/creat_project.py <project_name>
    python agent_builder/project_create/creat_project.py my_agent

会在沙盒容器 /workspace/<project_name>/ 下创建：
    <project_name>/
    ├── Agent/
    ├── Model/
    ├── Workflow/
    ├── Context/
    ├── Prompt/
    ├── Skill/
    ├── Config/
    ├── Finish_MarkDown/
    ├── Test/
    └── .env
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from project_template.project_templete import PROJECT_DIRS, PROJECT_FILES

SANDBOX_ROOT = PROJECT_ROOT / "sandbox"
sys.path.insert(0, str(SANDBOX_ROOT))
from sandbox_executor import SandboxExecutor  # type: ignore


def create_project(project_name: str, executor: SandboxExecutor | None = None) -> str:
    name = project_name.strip().replace(" ", "_")
    if not name:
        print("错误：project_name 不能为空", file=sys.stderr)
        sys.exit(1)

    exec_ = executor or SandboxExecutor()
    base = f"/workspace/{name}"

    # 创建所有目录
    for d in PROJECT_DIRS:
        path = f"{base}/{d}"
        exec_.run(["mkdir", "-p", path])
        print(f"已创建目录：{path}")

    # 创建占位文件
    for rel_path, content in PROJECT_FILES.items():
        container_path = f"{base}/{rel_path}"
        check = exec_.run(["test", "-f", container_path])
        if check.returncode == 0:
            print(f"已存在，跳过：{container_path}")
        else:
            result = exec_.write_file(container_path, content)
            if result.ok:
                print(f"已创建文件：{container_path}")
            else:
                print(f"写入失败：{container_path}\n{result.stderr}", file=sys.stderr)

    print(f"\n项目骨架已生成：{base}")
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 main_agent 项目骨架目录结构（写入沙盒容器）")
    parser.add_argument("project_name", help="项目名称，例如 my_agent")
    args = parser.parse_args()
    create_project(args.project_name)


if __name__ == "__main__":
    main()
