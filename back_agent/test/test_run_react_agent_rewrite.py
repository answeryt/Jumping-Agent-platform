"""
test_run_react_agent_rewrite.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
集成测试：验证 ReactAgentWorkflow 能否通过 python_batch 工具
实际改写 system_test/test_react_agent.py 中的版本标记。

测试流程（STEP 0-4）：
  STEP 0  加载配置（model_config.toml + .env）
  STEP 1  初始化 ReactAgentWorkflow（与 run_react_agent.py 保持一致）
  STEP 2  读取目标文件改写前内容（快照）
  STEP 3  给 Agent 下达改写命令，运行 Workflow
  STEP 4  断言目标文件版本标记已被实际修改

任务命令：
  将 system_test/test_react_agent.py 里的
    _AGENT_VERSION = "1.0.0"
  改写为
    _AGENT_VERSION = "1.0.1-rewritten"

运行方式：
  python back_agent/test/test_run_react_agent_rewrite.py

环境依赖：
  - back_agent/config/model_config.toml
  - back_agent/.env（包含 api_key 环境变量）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import sys
import textwrap
import traceback
from pathlib import Path
from typing import NoReturn, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.base_agent import PromptLoader
from agent.react import ReactAgentConfig
from config.settings import LLMConfig, load_settings
from Model.oepai import OpenAIModel
from workflow.flow_factory import FlowFactory

# ─── 目标文件与改写内容 ────────────────────────────────────────────────────────
AGENT_ROOT   = PROJECT_ROOT.parent                             # Desktop/agent
TARGET_FILE  = AGENT_ROOT / "system_test" / "test_react_agent.py"

OLD_MARKER   = '_AGENT_VERSION = "1.0.0"'
NEW_MARKER   = '_AGENT_VERSION = "1.0.1-rewritten"'

# 发给 agent 的改写任务：明确要求调用 python_batch 工具直接修改文件
USER_TASK = (
    "请使用 python_batch 工具完成以下文件修改任务：\n\n"
    f"  目标文件（绝对路径）: {TARGET_FILE.as_posix()}\n\n"
    "  改写规则:\n"
    f'    将文件中的字符串 {OLD_MARKER!r} 替换为 {NEW_MARKER!r}\n\n'
    "  python_batch 脚本示例（仅供参考，请根据实际情况调用工具）:\n"
    "    from pathlib import Path\n"
    f"    p = Path({str(TARGET_FILE)!r})\n"
    f"    p.write_text(p.read_text(encoding='utf-8').replace({OLD_MARKER!r}, {NEW_MARKER!r}), encoding='utf-8')\n"
    "    print('done')\n\n"
    "  请直接调用 tool_call(\"python_batch\", script=...) 完成修改，\n"
    "  最后输出 Final Answer 说明修改结果。"
)

# ─── 输出格式 ──────────────────────────────────────────────────────────────────
_SEP  = "═" * 70
_LINE = "─" * 70


def _banner(title: str) -> None:
    print(f"\n{_SEP}")
    print(f"  {title}")
    print(_SEP)


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _info(label: str, value: str) -> None:
    print(f"  ·  {label:<28}{value}")


def _fail(reason: str, exc: Optional[BaseException] = None) -> NoReturn:
    print(f"\n{_LINE}")
    print("  ✗  测试失败\n")
    for line in reason.strip().splitlines():
        print(f"     {line}")
    if exc is not None:
        print(f"\n  [异常类型]  {type(exc).__name__}: {exc}")
        print("\n  [完整堆栈]")
        traceback.print_exc()
    print(f"{_LINE}\n")
    sys.exit(1)


# ─── STEP 0：加载配置 ──────────────────────────────────────────────────────────

def _step0_load_config() -> LLMConfig:
    _banner("STEP 0  加载项目配置")
    try:
        settings = load_settings()
        llm = settings.llm_default
    except FileNotFoundError as e:
        _fail(
            "配置文件不存在。请确认以下文件已正确创建：\n"
            "  · back_agent/config/model_config.toml\n"
            "  · back_agent/.env",
            e,
        )
    except ValueError as e:
        _fail("配置内容有误（api_key 未设置或 model 字段为空）", e)
    except Exception as e:
        _fail("配置加载时发生意外错误", e)

    _info("model", llm.model)
    _info("base_url", llm.base_url or "(官方默认端点)")
    _info("stream", str(llm.stream))
    _ok("配置加载成功")
    return llm


# ─── STEP 1：初始化 Workflow ───────────────────────────────────────────────────

def _step1_build_workflow(llm: LLMConfig):  # type: ignore[return]
    _banner("STEP 1  初始化 ReactAgentWorkflow")
    try:
        model = OpenAIModel(verbose=True)
        prompt_loader = PromptLoader(prompt_dir=PROJECT_ROOT / "prompt")
        agent_config = ReactAgentConfig(prompt_file="react_agent_prompt.md")
        flow = FlowFactory.create(
            "react",
            model=model,
            agent_config=agent_config,
            prompt_loader=prompt_loader,
        )
    except FileNotFoundError as e:
        _fail("prompt 文件未找到，请确认 back_agent/prompt/react_agent_prompt.md 存在", e)
    except Exception as e:
        _fail("ReactAgentWorkflow 初始化失败", e)

    _ok("ReactAgentWorkflow 构建成功")
    return flow


# ─── STEP 2：读取改写前快照 ────────────────────────────────────────────────────

def _step2_snapshot_before() -> str:
    _banner("STEP 2  读取目标文件改写前快照")

    if not TARGET_FILE.exists():
        _fail(
            f"目标文件不存在: {TARGET_FILE}\n"
            "  请先运行一次 system_test/test_react_agent.py 以确保文件存在。"
        )

    content_before = _normalize_target_to_baseline()

    _info("目标文件", str(TARGET_FILE))
    _info("待替换标记", OLD_MARKER)
    _info("替换目标", NEW_MARKER)
    _ok(f"快照完成，标记存在于文件中")
    return content_before


def _normalize_target_to_baseline() -> str:
    """
    将目标文件规范化到测试基线状态（OLD_MARKER）。

    这样可以保证该集成测试可重复执行：
    - 若上次运行已写入 NEW_MARKER，本次会先自动回滚到 OLD_MARKER；
    - 若已是 OLD_MARKER，则直接继续；
    - 若两者都不存在，视为测试前置条件不满足，直接失败。
    """
    content = TARGET_FILE.read_text(encoding="utf-8")

    if OLD_MARKER in content:
        return content

    if NEW_MARKER in content:
        normalized = content.replace(NEW_MARKER, OLD_MARKER)
        TARGET_FILE.write_text(normalized, encoding="utf-8")
        _info("基线重置", f"检测到 {NEW_MARKER}，已回滚为 {OLD_MARKER}")
        return normalized

    _fail(
        "目标文件缺少可识别的版本标记，无法建立测试基线。\n\n"
        f"  预期至少包含其一:\n"
        f"    · {OLD_MARKER!r}\n"
        f"    · {NEW_MARKER!r}\n\n"
        f"  当前文件内容（前 500 字符）:\n"
        f"  {content[:500]!r}"
    )


# ─── STEP 3：运行 Workflow（改写任务）─────────────────────────────────────────

def _step3_run_rewrite(flow) -> str:
    _banner(
        "STEP 3  运行 ReactAgentWorkflow\n\n"
        f"  任务: 让 Agent 用 python_batch 改写 test_react_agent.py\n\n"
        "  （以下为 LLM 实时输出）"
    )
    print()

    try:
        answer: str = flow.run(USER_TASK)
    except Exception as e:
        _fail(
            "flow.run() 抛出异常，agent 调用链路出现问题。\n"
            "  常见原因：API key 无效、网络超时、模型服务不可用",
            e,
        )

    print(f"\n{_LINE}")
    print("  [Workflow Final Answer]")
    print(_LINE)
    print(textwrap.indent(answer.strip(), "  "))
    print(_LINE)

    if not answer.strip():
        _fail("flow.run() 返回了空字符串")

    _ok(f"Workflow 返回非空回答（{len(answer.strip())} 字符）")
    return answer


# ─── STEP 4：断言文件确实被改写 ───────────────────────────────────────────────

def _step4_assert_rewritten(content_before: str) -> None:
    _banner("STEP 4  断言目标文件已被 Agent 改写")

    content_after = TARGET_FILE.read_text(encoding="utf-8")

    if content_after == content_before:
        _fail(
            "目标文件内容与改写前完全相同，python_batch 工具未被调用或未生效。\n\n"
            "  可能原因：\n"
            "    · Agent 只描述了改写方法，没有实际调用 tool_call(\"python_batch\", ...)\n"
            "    · python_batch 脚本执行出错\n"
            "    · 文件路径不正确\n\n"
            f"  期望文件包含: {NEW_MARKER!r}"
        )

    if NEW_MARKER not in content_after:
        _fail(
            f"文件内容已改变，但未找到期望的新标记:\n"
            f"  期望: {NEW_MARKER!r}\n\n"
            f"  文件实际内容（含标记附近）:\n"
            + _extract_marker_context(content_after)
        )

    if OLD_MARKER in content_after:
        _fail(
            f"新标记写入成功，但旧标记仍残留于文件中:\n"
            f"  残留: {OLD_MARKER!r}\n"
            "  请检查 python_batch 脚本是否正确使用了 str.replace()。"
        )

    _ok(f"旧标记已不存在")
    _ok(f"新标记 {NEW_MARKER!r} 已写入文件")
    _ok("python_batch 代码改写工具调用成功！")


def _extract_marker_context(text: str, window: int = 200) -> str:
    """截取包含版本标记的上下文，便于排错输出。"""
    for marker in (NEW_MARKER, OLD_MARKER, "_AGENT_VERSION"):
        idx = text.find(marker)
        if idx >= 0:
            start = max(0, idx - window // 2)
            end   = min(len(text), idx + window // 2)
            return f"  ...{text[start:end]!r}..."
    return f"  (前 300 字符)\n  {text[:300]!r}"


# ─── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    llm             = _step0_load_config()
    flow            = _step1_build_workflow(llm)
    content_before  = _step2_snapshot_before()
    _step3_run_rewrite(flow)
    _step4_assert_rewritten(content_before)

    print(f"\n{_SEP}")
    print("  ✓  全部测试通过 —— Agent 代码改写工具验证成功！")
    print(f"{_SEP}\n")


if __name__ == "__main__":
    main()
