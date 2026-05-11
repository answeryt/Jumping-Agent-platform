"""
anchor_create.py

根据 agent 名称，从标准模板中提取该 agent 专属的锚点模板。

用法：
    python agent_builder/anchor_create/anchor_create.py <agent_name>
    python agent_builder/anchor_create/anchor_create.py interaction
    python agent_builder/anchor_create/anchor_create.py planning

逻辑：
    - 模板中业务锚点格式为 <!-- PREFIX_AGENT(S)_SUFFIX_START/END -->
    - 脚本保留匹配指定 agent 名称的锚点行，删除其他 agent 的锚点行
    - 非业务锚点（如 AGENT_CONTEXT_START 等结构锚点）保持不变
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "context_template" / "standard_markdown_template.md"

# 匹配业务锚点：<!-- SOMETHING_AGENT(S)_SUFFIX_START/END -->
# 捕获组1: 前缀(如 INTERACTION、PLANNING), 捕获组2: _AGENT或_AGENTS, 捕获组3: 后缀(如 _GOAL_START)
_BUSINESS_ANCHOR_RE = re.compile(
    r"^<!--\s+([A-Z][A-Z0-9]*)(_AGENTS?)(_[A-Z_]+(?:START|END))\s+-->$"
)


def normalize_agent_name(name: str) -> str:
    """规范化 agent 名称：去空格、连字符转下划线、转大写。"""
    return name.strip().lower().replace("-", "_").upper()


def extract_anchor_template(agent_name: str, template_content: str) -> str:
    """
    从模板内容中提取指定 agent 的专属锚点模板。

    保留：
      - 所有非业务锚点行（结构锚点、普通内容）
      - 匹配该 agent 名称的业务锚点行

    删除：
      - 其他 agent 的业务锚点行
    """
    prefix = normalize_agent_name(agent_name)
    result_lines = []

    for line in template_content.splitlines(keepends=True):
        m = _BUSINESS_ANCHOR_RE.match(line.strip())
        if m:
            line_prefix = m.group(1)  # 如 INTERACTION / PLANNING / ACTION
            if line_prefix == prefix:
                result_lines.append(line)
            # 其他 agent 的锚点行直接跳过（删除）
        else:
            result_lines.append(line)

    return "".join(result_lines)


def create_anchor_template(
    agent_name: str,
    template_path: Path = TEMPLATE_PATH,
    output_path: Path | None = None,
) -> str:
    """
    读取模板，生成指定 agent 的专属上下文模板，写入 output_path。

    返回生成的内容字符。
    """
    if not template_path.exists():
        raise FileNotFoundError(f"模板文件不存在：{template_path}")

    content = template_path.read_text(encoding="utf-8")
    result = extract_anchor_template(agent_name, content)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        print(f"已生成：{output_path}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="根据 agent 名称生成专属锚点模板")
    parser.add_argument("agent_name", help="agent 名称，例如 interaction 或 planning")
    parser.add_argument("--output", "-o", help="输出文件路径（可选）", default=None)
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else None
    create_anchor_template(args.agent_name, output_path=output_path)

    if output_path is None:
        # 无输出路径时打印到 stdout
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        print(extract_anchor_template(args.agent_name, content))


if __name__ == "__main__":
    main()
