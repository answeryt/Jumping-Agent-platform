"""
test_orchestrator_e2e.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
端对端测试：模拟用户在前端创建一个简单的单 Agent，
验证 orchestrator 后端的完整链路以及 ReactAgent 能否完成补全任务。

测试流程（STEP 0-4）：
  STEP 0  检测两个后端服务（ReactAgent API + Orchestrator）是否已启动
  STEP 1  发送 POST /create-agent 触发 orchestrator 完整编排流程
  STEP 2  验证 HTTP 响应结构（workspace / generated_files / answer）
  STEP 3  验证骨架文件已写入本地磁盘（backend/workspace/greeter/）
  STEP 4  验证 ReactAgent 已将 Agent 骨架补全（包含 run 方法且内容已改写）

模拟场景：
  用户填写 agent_name = "greeter"，点击"创建"。
  期望：orchestrator 生成骨架后驱动 ReactAgent 完善 GreeterAgent.run()。

运行前置条件（两个服务必须已启动）：
  终端 A：cd back_agent  && uvicorn api:app --host 0.0.0.0 --port 8000
  终端 B：cd backend    && uvicorn orchestrator:app --host 0.0.0.0 --port 8001

运行方式：
  python system_test/test_orchestrator_e2e.py

可选环境变量：
  ORCHESTRATOR_URL   Orchestrator 地址（默认 http://localhost:8001）
  REACT_AGENT_URL    ReactAgent 地址（默认 http://localhost:8000）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import importlib.util
import os
import sys
import textwrap
import traceback
from pathlib import Path
from typing import Any, Dict, NoReturn, Optional

import httpx

# ─── 路径配置 ──────────────────────────────────────────────────────────────────

PROJECT_ROOT        = Path(__file__).resolve().parent.parent
BACK_AGENT_ROOT     = PROJECT_ROOT / "back_agent"
AGENT_BUILDER_ROOT  = PROJECT_ROOT / "agent_builder"
BACKEND_WORKSPACE   = PROJECT_ROOT / "backend" / "workspace"

for _p in (str(BACK_AGENT_ROOT), str(AGENT_BUILDER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ─── 测试参数（模拟用户填写的表单） ────────────────────────────────────────────

AGENT_NAME: str       = "greeter"          # 用户填写的 agent 名称

ORCHESTRATOR_URL: str = os.getenv("ORCHESTRATOR_URL", "http://localhost:8001")
REACT_AGENT_URL: str  = os.getenv("REACT_AGENT_URL",  "http://localhost:8000")

# HTTP 超时：STEP 1 中 orchestrator 内部会调用 ReactAgent（最长 300 s），
# 此处再加 30 s 缓冲，避免客户端先超时。
REQUEST_TIMEOUT: float = 330.0

# ─── 输出辅助 ──────────────────────────────────────────────────────────────────

_SEP  = "═" * 70
_LINE = "─" * 70


def _banner(title: str) -> None:
    print(f"\n{_SEP}\n  {title}\n{_SEP}")


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _info(label: str, value: str) -> None:
    print(f"  ·  {label:<30}{value}")


def _warn(msg: str) -> None:
    print(f"  ⚠  {msg}")


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


# ─── 模板骨架内容（用于 STEP 4 比对） ──────────────────────────────────────────

def _load_builder_module(rel_path: str, name: str):
    """从 agent_builder/ 动态加载模块（避免与 back_agent 同名包冲突）。"""
    spec = importlib.util.spec_from_file_location(
        name, AGENT_BUILDER_ROOT / rel_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_skeleton_content() -> str:
    """
    生成 greeter_agent.py 的原始骨架内容（与 agent_builder 相同的模板函数），
    用于与 ReactAgent 改写后的文件进行比对。
    """
    _tpl_mod = _load_builder_module("agent_template/agent_templete.py", "agent_template")
    class_prefix = "".join(p.capitalize() for p in AGENT_NAME.split("_"))
    return _tpl_mod.agent_py(class_prefix, AGENT_NAME, f"{AGENT_NAME}_agent.md")


# ─── STEP 0：检测两个服务是否已启动 ───────────────────────────────────────────

def _step0_check_services() -> None:
    _banner("STEP 0  检测后端服务可达性")

    services = [
        ("ReactAgent API",   f"{REACT_AGENT_URL}/docs"),
        ("Orchestrator API", f"{ORCHESTRATOR_URL}/docs"),
    ]

    for service_name, url in services:
        try:
            r = httpx.get(url, timeout=5.0)
            if r.status_code < 500:
                _ok(f"{service_name} 已启动  ({url})")
            else:
                _fail(
                    f"{service_name} 返回异常状态码 {r.status_code}。\n"
                    f"请确认服务已正常启动：{url}"
                )
        except httpx.ConnectError:
            _fail(
                f"无法连接到 {service_name}：{url}\n\n"
                "请先启动两个服务：\n"
                "  终端 A（back_agent/）：uvicorn api:app --host 0.0.0.0 --port 8000\n"
                "  终端 B（backend/）：  uvicorn orchestrator:app --host 0.0.0.0 --port 8001"
            )
        except Exception as e:
            _fail(f"检测 {service_name} 时发生意外错误", e)

    _info("Orchestrator 地址", ORCHESTRATOR_URL)
    _info("ReactAgent 地址",   REACT_AGENT_URL)
    _info("模拟创建 agent",    AGENT_NAME)


# ─── STEP 1：POST /create-agent（模拟用户点击创建）────────────────────────────

def _step1_create_agent() -> Dict[str, Any]:
    _banner(
        f"STEP 1  模拟用户创建 Agent\n\n"
        f"  POST {ORCHESTRATOR_URL}/create-agent\n"
        f"  Body: {{ \"agent_name\": \"{AGENT_NAME}\" }}"
    )

    payload = {"agent_name": AGENT_NAME}

    try:
        resp = httpx.post(
            f"{ORCHESTRATOR_URL}/create-agent",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except httpx.ReadTimeout:
        _fail(
            f"请求超时（{REQUEST_TIMEOUT}s）。\n"
            "可能原因：ReactAgent 处理时间过长或模型服务无响应。\n"
            "可适当增大 REQUEST_TIMEOUT 或检查模型 API 连通性。"
        )
    except Exception as e:
        _fail("POST /create-agent 时发生意外异常", e)

    _info("HTTP 状态码", str(resp.status_code))

    if resp.status_code != 200:
        _fail(
            f"Orchestrator 返回非 200（{resp.status_code}）。\n"
            f"响应体：\n{textwrap.indent(resp.text[:800], '  ')}"
        )

    try:
        data: Dict[str, Any] = resp.json()
    except Exception as e:
        _fail("响应体不是合法 JSON", e)

    _ok(f"请求成功，响应体已解析（共 {len(resp.text)} 字节）")
    return data


# ─── STEP 2：验证响应结构 ──────────────────────────────────────────────────────

def _step2_validate_response(data: Dict[str, Any]) -> Path:
    _banner("STEP 2  验证 HTTP 响应结构")

    required_keys = ("workspace", "generated_files", "answer")
    missing = [k for k in required_keys if k not in data]
    if missing:
        _fail(f"响应体缺少必填字段：{missing}\n完整响应：{data}")

    workspace_str: str      = data["workspace"]
    generated_files: list   = data["generated_files"]
    answer: str             = data["answer"]

    _info("workspace",       workspace_str)
    _info("generated_files", str(generated_files))
    _info("answer 长度",     f"{len(answer.strip())} 字符")

    if not workspace_str:
        _fail("响应字段 workspace 为空")
    if not isinstance(generated_files, list) or not generated_files:
        _fail(f"响应字段 generated_files 为空列表或类型有误：{generated_files!r}")
    if not answer.strip():
        _fail("响应字段 answer 为空，ReactAgent 未返回任何内容")

    workspace_path = Path(workspace_str)

    agent_file_rel = f"Agent/{AGENT_NAME}_agent.py"
    prompt_file_rel = f"Prompt/{AGENT_NAME}_agent.md"
    for expected in (agent_file_rel, prompt_file_rel):
        if expected not in generated_files:
            _warn(f"generated_files 中未找到预期条目：{expected}")

    _ok("workspace 字段非空")
    _ok(f"generated_files 包含 {len(generated_files)} 个条目")
    _ok(f"answer 非空（{len(answer.strip())} 字符）")

    print(f"\n{_LINE}\n  [Orchestrator Final Answer]\n{_LINE}")
    print(textwrap.indent(answer.strip()[:600], "  "))
    if len(answer.strip()) > 600:
        print("  ... （已截断，仅显示前 600 字符）")
    print(_LINE)

    return workspace_path


# ─── STEP 3：验证文件已写入磁盘 ───────────────────────────────────────────────

def _step3_validate_files(workspace_path: Path) -> Path:
    _banner("STEP 3  验证骨架文件已写入磁盘")

    _info("workspace 目录", str(workspace_path))

    if not workspace_path.exists():
        _fail(
            f"workspace 目录不存在：{workspace_path}\n"
            "orchestrator 可能在创建目录时发生错误，请检查服务日志。"
        )

    expected_files = [
        (workspace_path / "Agent"  / f"{AGENT_NAME}_agent.py", "Agent 文件"),
        (workspace_path / "Prompt" / f"{AGENT_NAME}_agent.md", "Prompt 文件"),
    ]

    all_exist = True
    for fpath, label in expected_files:
        if fpath.exists():
            size = fpath.stat().st_size
            _ok(f"{label} 已存在  ({fpath.relative_to(PROJECT_ROOT)}, {size} bytes)")
        else:
            _warn(f"{label} 不存在：{fpath}")
            all_exist = False

    if not all_exist:
        _fail(
            "部分文件未生成。可能原因：\n"
            "  · agent_builder 写入失败（检查 orchestrator 服务日志）\n"
            "  · workspace 路径权限问题"
        )

    agent_file = workspace_path / "Agent" / f"{AGENT_NAME}_agent.py"
    return agent_file


# ─── STEP 4：验证 ReactAgent 已补全 Agent 骨架 ────────────────────────────────

def _step4_validate_improvement(agent_file: Path) -> None:
    _banner("STEP 4  验证 ReactAgent 已补全 Agent 骨架")

    actual_content = agent_file.read_text(encoding="utf-8")
    skeleton_content = _get_skeleton_content()

    _info("文件大小（原始骨架）", f"{len(skeleton_content)} 字节")
    _info("文件大小（改写后）",   f"{len(actual_content)} 字节")

    checks_passed = True

    # 检查 1：内容与原始骨架不同（已被改写）
    if actual_content.strip() == skeleton_content.strip():
        _warn(f"{agent_file.name} 内容与原始骨架完全相同，ReactAgent 未写回该文件")
        checks_passed = False
    else:
        _ok(f"{agent_file.name} 内容已与骨架不同（已被改写）")

    # 检查 2：包含 run 方法（核心业务逻辑已补全）
    if "def run(" not in actual_content:
        _warn(f"{agent_file.name} 缺少 run 方法，补全不完整")
        checks_passed = False
    else:
        _ok(f"{agent_file.name} 包含 run 方法")

    # 检查 3：文件长度合理（有实质内容，不是空实现）
    min_length = len(skeleton_content) + 50
    if len(actual_content) < min_length:
        _warn(
            f"{agent_file.name} 内容较短（{len(actual_content)} 字节），"
            f"可能补全内容不足（期望 > {min_length} 字节）"
        )
        checks_passed = False
    else:
        _ok(f"{agent_file.name} 内容长度合理（{len(actual_content)} 字节）")

    # 打印改写后文件的摘要（前 20 行）
    print(f"\n{_LINE}\n  [{agent_file.name} 改写后内容（前 20 行）]\n{_LINE}")
    lines = actual_content.splitlines()
    for ln in lines[:20]:
        print(f"  {ln}")
    if len(lines) > 20:
        print(f"  ... （共 {len(lines)} 行，仅显示前 20 行）")
    print(_LINE)

    if not checks_passed:
        _fail(
            "Agent 文件未被充分补全。可能原因：\n"
            "  · ReactAgent 未成功调用 load_project 或路径有误，write_file 未找到目标文件\n"
            "  · 模型输出格式有误，write_file 解析内容失败\n"
            "  · 建议查看 Orchestrator 服务日志，确认 load_project / get / write_file 是否均返回 [OK]"
        )


# ─── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _banner(
        "端对端测试：模拟用户创建单 Agent\n\n"
        f"  场景：用户填写 agent_name={AGENT_NAME!r}\n"
        "  覆盖：orchestrator 编排 → agent_builder 生成骨架 → ReactAgent 补全"
    )

    _step0_check_services()

    data          = _step1_create_agent()
    workspace     = _step2_validate_response(data)
    agent_file    = _step3_validate_files(workspace)
    _step4_validate_improvement(agent_file)

    print(f"\n{_SEP}")
    print("  ✓  全部步骤通过 —— 单 Agent 创建端对端测试完成！")
    print(f"  ·  生成文件位于：{workspace}")
    print(f"{_SEP}\n")


if __name__ == "__main__":
    main()
