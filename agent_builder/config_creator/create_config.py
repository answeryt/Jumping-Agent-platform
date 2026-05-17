"""
create_config.py

用法：
    python agent_builder/config_creator/create_config.py <project_name>
    python agent_builder/config_creator/create_config.py my_agent

会自动生成（写入沙盒容器 /workspace/<project_name>/runtime/Config/）：
    Config/model_config.toml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config_template.config_templete import model_config_toml

SANDBOX_ROOT = PROJECT_ROOT / "sandbox"
sys.path.insert(0, str(SANDBOX_ROOT))
from sandbox_executor import SandboxExecutor  # type: ignore


def create_config(project_name: str, executor: SandboxExecutor | None = None) -> None:
    name = project_name.strip().replace(" ", "_")
    if not name:
        print("错误：project_name 不能为空", file=sys.stderr)
        sys.exit(1)

    exec_ = executor or SandboxExecutor()
    config_dir = f"/workspace/{name}/runtime/Config"

    model_path = f"{config_dir}/model_config.toml"

    # 写入 model_config.toml
    check = exec_.run(["test", "-f", model_path])
    if check.returncode == 0:
        print(f"已存在，跳过：{model_path}")
    else:
        result = exec_.write_file(model_path, model_config_toml())
        if result.ok:
            print(f"已生成：{model_path}")
        else:
            print(f"写入失败：{model_path}\n{result.stderr}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Config 配置文件骨架（写入沙盒容器）")
    parser.add_argument("project_name", help="项目名称，例如 my_agent")
    args = parser.parse_args()
    create_config(args.project_name)


if __name__ == "__main__":
    main()
