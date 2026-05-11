"""
test_react_agent_code_tools.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
端到端集成测试（已适配 ReAct 多轮循环架构 + ShellTool 工具集）

测试分为两个独立部分：

第一部分：Workflow 端到端测试（STEP 0-2）
  验证 ReactAgentWorkflow 完整执行链路（含内部工具调用）正常运行，
  最终返回的 Final Answer 非空且有实质内容。
  新架构下 flow.run() 在内部完成 ReAct 多轮循环（含真实工具调用），
  返回的 Final Answer 文本中不再包含 tool_call(...)，这是正确行为。

第二部分：ShellTool 独立测试（STEP 3-5）
  直接测试工具层，用确定性指令验证 ShellTool 各方法可正常执行，
  与 LLM 输出格式完全无关。

运行方式：
  python back_agent/test/test_react_agent_code_tools.py

环境依赖：
  - back_agent/config/model_config.toml  （模型 & base_url 配置）
  - back_agent/.env                       （包含 api_key 环境变量）
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
from tools.code_tools import ShellResult, ShellTool
from tools.shell_tool_adapter import build_shell_bridge
from workflow.flow_factory import FlowFactory

# ─── 测试用例输入 ──────────────────────────────────────────────────────────────
USER_TASK = "帮我写一个单一agent框架"

# ShellTool 独立测试使用的确定性脚本
SHELL_TEST_SCRIPT = (
    "result = []\n"
    "a, b = 0, 1\n"
    "for _ in range(10):\n"
    "    result.append(a)\n"
    "    a, b = b, a + b\n"
    "print(result)"
)
SHELL_TEST_EXPECTED = ["0", "1", "2", "3", "5", "8", "13", "21", "34"]

# ─── 输出格式工具 ──────────────────────────────────────────────────────────────
_SEP  = "═" * 70
_LINE = "─" * 70


def _banner(title: str) -> None:
    print(f"\n{_SEP}")
    print(f"  {title}")
    print(_SEP)


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _info(label: str, value: str) -> None:
    print(f"  ·  {label:<24}{value}")


def _section(title: str) -> None:
    print(f"\n  ── {title}")


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


# ─── 第一部分：Workflow 端到端测试 ────────────────────────────────────────────

def _step0_load_config() -> LLMConfig:
    """STEP 0：加载 model_config.toml + .env 配置。"""
    _banner("STEP 0  加载项目配置")
    try:
        settings = load_settings()
        llm = settings.llm_default
    except FileNotFoundError as e:
        _fail(
            "配置文件不存在。请确认以下文件已正确创建：\n"
            "  · back_agent/config/model_config.toml\n"
            "  · back_agent/.env（包含 API key 环境变量）",
            e,
        )
    except ValueError as e:
        _fail(
            "配置内容有误，常见原因：\n"
            "  · model_config.toml 中 api_key_env 指向的环境变量未在 .env 中设置\n"
            "  · model 字段为空",
            e,
        )
    except Exception as e:
        _fail("配置加载时发生意外错误", e)

    _info("model", llm.model)
    _info("base_url", llm.base_url or "(官方默认端点)")
    _info("stream", str(llm.stream))
    _ok("配置加载成功")
    return llm


def _step1_build_workflow(llm: LLMConfig):  # type: ignore[return]
    """STEP 1：与 run_react_agent.py 使用完全相同的方式初始化 workflow。"""
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
        _fail(
            "prompt 文件未找到。请确认 back_agent/prompt/react_agent_prompt.md 存在。",
            e,
        )
    except Exception as e:
        _fail("ReactAgentWorkflow 初始化失败", e)

    _ok("ReactAgentWorkflow 构建成功")
    _info("flow_type", "react")
    _info("prompt_file", "react_agent_prompt.md")
    return flow


def _step2_run_agent_e2e(flow) -> str:
    """STEP 2：端到端运行 Workflow，验证 Final Answer 非空且有实质内容。

    新架构说明：
      flow.run() 内部完成 ReAct 多轮循环（含真实工具调用），
      返回的是最终的 Final Answer 文本，不再包含 tool_call(...)。
      因此本步骤只验证回答非空且有实质内容，不做 tool_call 格式检查。
    """
    _banner(f'STEP 2  端到端运行 Workflow\n\n  「{USER_TASK}」\n\n  （以下为 LLM 实时输出）')
    print()

    try:
        answer: str = flow.run(USER_TASK)
    except Exception as e:
        _fail(
            "flow.run() 抛出异常，agent 调用链路出现问题。\n\n"
            "  常见原因：\n"
            "    · API key 无效或过期\n"
            "    · 网络连接超时\n"
            "    · 模型服务暂不可用",
            e,
        )

    print(f"\n{_LINE}")
    print("  [Workflow 最终回答（Final Answer）]")
    print(_LINE)
    print(textwrap.indent(answer.strip(), "  "))
    print(_LINE)

    if not answer.strip():
        _fail(
            "flow.run() 返回了空字符串。\n\n"
            "  可能原因：\n"
            "    · 模型返回了空 content\n"
            "    · _run_with_tools() 循环未正常终止，last_reply 为空"
        )
    _ok("Workflow 成功返回非空回答")

    if len(answer.strip()) < 100:
        _fail(
            f"回答内容过短（{len(answer.strip())} 字符），可能工具调用未完成或推理循环异常。\n\n"
            f"  实际回答: {answer.strip()!r}"
        )
    _ok(f"回答内容充实（{len(answer.strip())} 字符），Workflow E2E 验证通过")
    return answer


# ─── 第二部分：ShellTool 独立测试 ─────────────────────────────────────────────

def _step3_init_shell_tool() -> ShellTool:
    """STEP 3：直接初始化 ShellTool，验证工具层可独立实例化。"""
    _banner("STEP 3  初始化 ShellTool（独立验证）")
    try:
        tool = ShellTool()
    except Exception as e:
        _fail("ShellTool 初始化时发生意外错误", e)

    _info("default_cwd", tool.default_cwd or "(当前目录)")
    _info("timeout", str(tool.timeout))
    _ok("ShellTool 初始化成功")
    return tool


def _step4_execute_python_batch(tool: ShellTool) -> ShellResult:
    """STEP 4：调用 python_batch 执行确定性脚本，验证本地 Python 可正常运行。"""
    _banner("STEP 4  执行 ShellTool.python_batch()")
    _section("测试脚本")
    print(textwrap.indent(SHELL_TEST_SCRIPT, "    "))
    print()

    try:
        result = tool.python_batch(SHELL_TEST_SCRIPT)
    except Exception as e:
        _fail("python_batch() 抛出异常", e)

    _section("执行结果")
    _info("returncode", str(result.returncode))
    _info("ok", str(result.ok))
    if result.stdout.strip():
        print(f"\n  [stdout]\n{textwrap.indent(result.stdout.strip(), '    ')}")
    if result.stderr.strip():
        print(f"\n  [stderr]\n{textwrap.indent(result.stderr.strip(), '    ')}")
    print()
    return result


def _step5_assert(result: ShellResult) -> None:
    """STEP 5：对 ShellTool.python_batch 执行结果做精准断言。"""
    _banner("STEP 5  断言验证")

    if not result.ok:
        _fail(
            f"python_batch() 执行失败（returncode={result.returncode}）。\n\n"
            f"  stderr: {result.stderr.strip()!r}\n\n"
            "  请确认本地 Python 解释器可用。"
        )
    _ok(f"returncode=0，执行成功")

    if not result.stdout.strip():
        _fail(
            "stdout 为空字符串，脚本未产生任何输出。\n\n"
            "  请检查 ShellTool.python_batch() 的 exec_script 调用链路。"
        )
    _ok("stdout 非空，脚本有实际输出")

    output = result.stdout
    missing = [v for v in SHELL_TEST_EXPECTED if v not in output]
    if missing:
        _fail(
            f"stdout 中未发现斐波那契数列期望值: {missing}\n\n"
            f"  实际输出: {output.strip()!r}\n\n"
            "  脚本应 print 出 [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]。"
        )
    _ok("stdout 包含正确的斐波那契数列（确定性验证通过）")

    # 额外验证：build_shell_bridge 可以构建出注册了所有工具的 bridge
    _section("验证 build_shell_bridge 工具注册")
    bridge = build_shell_bridge()
    required = ("run", "bash", "exec_script", "sed", "perl_replace",
                "python_batch", "git_diff", "grep", "ripgrep")
    missing_tools = [n for n in required if not bridge.has_tool(n)]
    if missing_tools:
        _fail(f"build_shell_bridge() 缺少以下工具注册: {missing_tools}")
    _ok(f"build_shell_bridge() 已注册全部 {len(required)} 个工具")


# ─── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    llm    = _step0_load_config()
    flow   = _step1_build_workflow(llm)
    _step2_run_agent_e2e(flow)               # 第一部分：Workflow E2E
    tool   = _step3_init_shell_tool()        # 第二部分：ShellTool 独立测试
    result = _step4_execute_python_batch(tool)
    _step5_assert(result)

    print(f"\n{_SEP}")
    print("  ✓  全部测试通过 —— Workflow E2E + ShellTool 均验证成功！")
    print(f"{_SEP}\n")


if __name__ == "__main__":
    main()
