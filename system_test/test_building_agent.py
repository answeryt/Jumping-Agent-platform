"""
test_building_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
集成测试：先用 agent_builder 在 system_test/agent_test/ 生成代码骨架，
再通过 ReactAgentWorkflow（与 run_react_agent.py 初始化方式一致）读取
骨架文件并补全其业务逻辑，最后断言文件内容已被实际改写。

测试流程（STEP 0-4）：
  STEP 0  加载配置（model_config.toml + .env）
  STEP 1  用 agent_builder 生成代码骨架到 system_test/agent_test/
  STEP 2  初始化 ReactAgentWorkflow（复用 run_react_agent.py 的构建方式）
  STEP 3  向 Agent 下达完善任务，运行 Workflow
  STEP 4  断言骨架文件已被 Agent 实际改写

运行方式：
  python system_test/test_building_agent.py

环境依赖：
  - back_agent/config/model_config.toml
  - back_agent/.env（含 api_key 环境变量）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import importlib.util
import sys
import textwrap
import traceback
from pathlib import Path
from typing import NoReturn, Optional

# ─── 路径配置 ──────────────────────────────────────────────────────────────────

PROJECT_ROOT       = Path(__file__).resolve().parent.parent
BACK_AGENT_ROOT    = PROJECT_ROOT / "back_agent"
AGENT_BUILDER_ROOT = PROJECT_ROOT / "agent_builder"
AGENT_TEST_DIR     = Path(__file__).resolve().parent / "agent_test"

for _p in (str(BACK_AGENT_ROOT), str(AGENT_BUILDER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 以下模块位于 back_agent/ 子目录，通过 sys.path 在运行时解析。
# 静态分析器（basedpyright）不执行 sys.path 修改，因此无法静态定位这些包，
# 使用 type: ignore 消除误报；运行时导入完全正常。
from agent.base_agent import PromptLoader          # type: ignore[import-untyped]  # noqa: E402
from agent.react import ReactAgentConfig           # type: ignore[import-untyped]  # noqa: E402
from config.settings import LLMConfig, load_settings  # type: ignore[import-untyped]  # noqa: E402
from Model.oepai import OpenAIModel                # type: ignore[import-untyped]  # noqa: E402
from workflow.flow_factory import FlowFactory      # type: ignore[import-untyped]  # noqa: E402


# ─── agent_builder 模块动态加载（避免与 back_agent 路径冲突）─────────────────

def _load_builder_module(rel_path: str, name: str):
    """从 agent_builder/ 下按相对路径加载模块。"""
    spec = importlib.util.spec_from_file_location(
        name, AGENT_BUILDER_ROOT / rel_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── LocalExecutor（将 SandboxExecutor 容器路径映射到本地文件系统）───────────

class _ExecResult:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout    = stdout
        self.stderr    = stderr
        self.returncode = returncode

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class LocalExecutor:
    """把 /workspace/... 路径重定向到 base_dir，直接写本地磁盘。"""

    _PREFIX = "/workspace/"

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def _to_local(self, container_path: str) -> Path:
        if container_path.startswith(self._PREFIX):
            rel = container_path[len(self._PREFIX):]
        else:
            rel = container_path.lstrip("/")
        return self.base_dir / rel

    def run(self, command: list, **_kwargs) -> _ExecResult:
        if command[:2] == ["test", "-f"]:
            exists = self._to_local(command[2]).exists()
            return _ExecResult(returncode=0 if exists else 1)
        if command[:2] == ["mkdir", "-p"]:
            self._to_local(command[2]).mkdir(parents=True, exist_ok=True)
            return _ExecResult()
        return _ExecResult()

    def write_file(self, container_path: str, content: str) -> _ExecResult:
        local = self._to_local(container_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(content, encoding="utf-8")
        return _ExecResult()


# ─── 输出辅助 ──────────────────────────────────────────────────────────────────

_SEP  = "═" * 70
_LINE = "─" * 70


def _banner(title: str) -> None:
    print(f"\n{_SEP}\n  {title}\n{_SEP}")


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _info(label: str, value: str) -> None:
    print(f"  ·  {label:<28}{value}")


def _fail(reason: str, exc: Optional[BaseException] = None) -> NoReturn:
    print(f"\n{_LINE}\n  ✗  测试失败\n")
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
            "配置文件不存在，请确认以下文件已正确创建：\n"
            "  · back_agent/config/model_config.toml\n"
            "  · back_agent/.env",
            e,
        )
    except ValueError as e:
        _fail("配置内容有误（api_key 未设置或 model 字段为空）", e)
    except Exception as e:
        _fail("配置加载时发生意外错误", e)

    _info("model",    llm.model)
    _info("base_url", llm.base_url or "(官方默认端点)")
    _info("stream",   str(llm.stream))
    _ok("配置加载成功")
    return llm


# ─── STEP 1：agent_builder 生成代码骨架 ───────────────────────────────────────

def _step1_generate_skeleton() -> Path:
    """
    用 agent_builder 的 create_agent 在 AGENT_TEST_DIR 生成骨架。
    每次运行前先删除旧骨架，确保 Agent 始终面对原始骨架文件。
    返回 agent_file 路径供后续步骤使用。
    """
    _banner("STEP 1  用 agent_builder 生成代码骨架")

    AGENT_TEST_DIR.mkdir(parents=True, exist_ok=True)

    # 每次测试前强制重置骨架，避免上次 Agent 改写结果干扰本轮断言
    _targets = [
        AGENT_TEST_DIR / "Agent" / "summarizer_agent.py",
    ]
    for f in _targets:
        if f.exists():
            f.unlink()
            _info("重置", f"已删除旧骨架: {f.relative_to(PROJECT_ROOT)}")

    executor = LocalExecutor(AGENT_TEST_DIR)

    # 动态加载 builder 模块（避免与 back_agent 同名模块冲突）
    _agent_mod = _load_builder_module("agent_create/create_agent.py", "builder_create_agent")

    # 生成 summarizer agent 骨架
    _agent_mod.create_agent("summarizer", executor=executor)

    agent_file = AGENT_TEST_DIR / "Agent" / "summarizer_agent.py"

    if not agent_file.exists():
        _fail(f"骨架文件未生成: {agent_file}")
    _ok(f"已生成: {agent_file.relative_to(PROJECT_ROOT)}")

    return agent_file


# ─── STEP 2：初始化 ReactAgentWorkflow ────────────────────────────────────────

def _step2_build_workflow(llm: LLMConfig):  # type: ignore[return]
    _banner("STEP 2  初始化 ReactAgentWorkflow（与 run_react_agent.py 一致）")
    try:
        model        = OpenAIModel(verbose=True)
        prompt_loader = PromptLoader(prompt_dir=BACK_AGENT_ROOT / "prompt")
        agent_config  = ReactAgentConfig(prompt_file="react_agent_prompt.md")
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


# ─── STEP 3：运行 ReactAgent 完善代码 ─────────────────────────────────────────

def _build_user_task(agent_file: Path) -> str:
    """
    给 ReactAgent 的用户任务提示词，指导其使用沙盒工具（load_project / get /
    write_file）读取和改写骨架文件。

    设计原则：
      第 1 行 — 项目架构背景，让 Agent 知道代码要符合哪种规范。
      第 2 行 — 路径约束提示（Windows 正斜杠）。
      第 3‑5 行 — 三步操作：load_project → get → write_file / patch_symbol。
      最后一行 — Final Answer 汇报要求。
    """
    test_dir = agent_file.parent.parent.as_posix()
    return (
        "本项目是基于 ReAct 循环的多 Agent 框架：Agent 从 Prompt/*.md 读取系统指令，"
        "骨架代码由 agent_builder 自动生成，需 AI 补全业务逻辑。\n"
        "【重要】当前运行环境为 Windows，tool_call 参数中的所有文件路径必须使用正斜杠（/），"
        "禁止使用反斜杠（\\），否则工具调用会解析失败。\n"
        f"请按以下步骤操作：\n"
        f"① 调用 load_project 加载骨架目录：{test_dir}\n"
        f"② 调用 get 读取骨架文件的当前内容：\n"
        f"   · {agent_file.as_posix()}（SummarizerAgent）\n"
        f"③ 用 write_file（或 patch_symbol）将补全后的完整代码写回原文件：\n"
        f"   · SummarizerAgent 需实现完整的 run 方法：加载 Prompt，调用模型，返回精简摘要\n"
        "完成后输出 Final Answer 说明文件的改写要点。"
    )


def _read_snapshot(agent_file: Path) -> str:
    """读取骨架文件的原始内容快照，供 STEP 4 比对。"""
    return agent_file.read_text(encoding="utf-8")


def _step3_run_agent(flow, agent_file: Path) -> str:
    _banner("STEP 3  ReactAgent 读取并完善生成代码\n\n  （以下为 LLM 实时输出）")

    user_task = _build_user_task(agent_file)

    print("\n  [用户任务]")
    for line in user_task.strip().splitlines():
        print(f"    {line}")
    print()

    try:
        answer = flow.run(user_task)
    except Exception as e:
        _fail(
            "flow.run() 抛出异常，agent 调用链路出现问题。\n"
            "  常见原因：API key 无效、网络超时、模型服务不可用",
            e,
        )

    print(f"\n{_LINE}\n  [Workflow Final Answer]\n{_LINE}")
    print(textwrap.indent(answer.strip(), "  "))
    print(_LINE)

    if not answer.strip():
        _fail("flow.run() 返回了空字符串")

    _ok(f"Workflow 返回非空回答（{len(answer.strip())} 字符）")
    return answer


# ─── STEP 4：断言文件已被改写 ──────────────────────────────────────────────────

def _step4_assert_improved(
    agent_file: Path,
    agent_snapshot: str,
) -> None:
    _banner("STEP 4  断言骨架文件已被 Agent 改写完善")

    agent_content = agent_file.read_text(encoding="utf-8")

    all_pass = True

    # ── Agent 文件：内容必须与原始骨架不同，且包含 run 方法 ──
    if agent_content == agent_snapshot:
        _info("警告", f"{agent_file.name} 内容与骨架完全相同，Agent 未写回该文件")
        all_pass = False
    elif "def run(" not in agent_content:
        _info("警告", f"{agent_file.name} 已改写但缺少 run 方法，补全不完整")
        all_pass = False
    else:
        _ok(f"{agent_file.name} 已改写且包含 run 方法")

    if not all_pass:
        _fail(
            "部分骨架文件未被完善。可能原因：\n"
            "  · Agent 未调用 load_project 或路径传入有误，导致 write_file 找不到项目根\n"
            "  · Agent 调用了 write_file 但文件内容含非法转义序列（路径反斜杠）导致解析失败\n"
            "  · 建议检查 Observation 日志确认 load_project / get / write_file 是否均返回 [OK]"
        )


# ─── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    llm                        = _step0_load_config()
    agent_file                 = _step1_generate_skeleton()
    agent_snapshot             = _read_snapshot(agent_file)
    flow                       = _step2_build_workflow(llm)
    _step3_run_agent(flow, agent_file)
    _step4_assert_improved(agent_file, agent_snapshot)

    print(f"\n{_SEP}")
    print("  ✓  全部步骤通过 —— agent_builder + ReactAgent 集成测试完成！")
    print(f"{_SEP}\n")


if __name__ == "__main__":
    main()
