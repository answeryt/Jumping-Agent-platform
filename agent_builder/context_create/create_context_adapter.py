"""
create_context_adapter.py

用法：
    python agent_builder/context_create/create_context_adapter.py
    python agent_builder/context_create/create_context_adapter.py --force

作用：
    自动创建 /workspace/Context/standard_markdown.md 全局上下文模板（写入沙盒容器）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

SANDBOX_ROOT = PROJECT_ROOT / "sandbox"
sys.path.insert(0, str(SANDBOX_ROOT))
from sandbox_executor import SandboxExecutor  # type: ignore

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "context_template" / "standard_markdown_template.md"
CONTAINER_PATH = "/workspace/Context/standard_markdown.md"


def create_context_adapter(force: bool = False, executor: SandboxExecutor | None = None) -> str:
    exec_ = executor or SandboxExecutor()

    check = exec_.run(["test", "-f", CONTAINER_PATH])
    if check.returncode == 0 and not force:
        print(f"已存在，跳过：{CONTAINER_PATH}")
        return CONTAINER_PATH

    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    result = exec_.write_file(CONTAINER_PATH, content)
    if result.ok:
        print(f"{'已覆盖' if force else '已生成'}：{CONTAINER_PATH}")
    else:
        print(f"写入失败：{CONTAINER_PATH}\n{result.stderr}", file=sys.stderr)

    return CONTAINER_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="自动生成标准全局 Markdown 上下文模板（写入沙盒容器）")
    parser.add_argument("--force", action="store_true", help="若目标文件已存在则覆盖")
    args = parser.parse_args()
    create_context_adapter(force=args.force)


if __name__ == "__main__":
    main()