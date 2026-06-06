from __future__ import annotations

from typing import Optional, Tuple

try:
    from .sandbox_diagnostic_tools import (
        build_sandbox_diagnostics_tool,
        _SANDBOX_DIAGNOSTIC_TOOL_NAMES,
    )
    from .sandbox_tools import SandboxTool, build_sandbox_tool, _SANDBOX_TOOL_NAMES
    from .sandbox_write_tools import (
        SandboxWriteTool,
        build_sandbox_write_tool,
        _SANDBOX_WRITE_TOOL_NAMES,
    )
    from .tool_bridge import ToolBridge
except ImportError:  # pragma: no cover - legacy top-level imports
    from tools.sandbox_diagnostic_tools import (
        build_sandbox_diagnostics_tool,
        _SANDBOX_DIAGNOSTIC_TOOL_NAMES,
    )
    from tools.sandbox_tools import SandboxTool, build_sandbox_tool, _SANDBOX_TOOL_NAMES
    from tools.sandbox_write_tools import (
        SandboxWriteTool,
        build_sandbox_write_tool,
        _SANDBOX_WRITE_TOOL_NAMES,
    )
    from tools.tool_bridge import ToolBridge


def build_shell_bridge() -> ToolBridge:
    try:
        from .code_tools import ShellResult, ShellTool
    except ImportError:  # pragma: no cover - legacy top-level imports
        from tools.code_tools import ShellResult, ShellTool

    tool = ShellTool()
    bridge = ToolBridge()

    def _as_dict(result: ShellResult) -> dict[str, object]:
        return result.to_dict()

    for name in (
        "run",
        "bash",
        "exec_script",
        "sed",
        "perl_replace",
        "python_batch",
        "git_diff",
        "grep",
        "ripgrep",
    ):
        bridge.register_tool(
            name,
            lambda *args, _name=name, **kwargs: _as_dict(getattr(tool, _name)(*args, **kwargs)),
        )
    return bridge


def build_sandbox_bridge(
    sandbox: Optional[SandboxTool] = None,
) -> Tuple[ToolBridge, SandboxTool]:
    """
    构造一个注册了全套沙盒工具（读 + 写 + 运行/诊断）的 ToolBridge。

    读工具（来自 SandboxTool）：
    - load_project : 将本地项目加载到沙盒（扫描、建符号索引、解析配置）
    - tree         : 展示项目目录树，.py 文件附带顶层类名
    - find         : 精准定位符号 / 文件 / 文本（三级 fallback）
    - get          : 取出类 / 函数 / 文件 / 行号附近的代码段
    - config       : 展示配置快照（.env/.toml/.json，自动脱敏）

    写工具（来自 SandboxWriteTool，与读工具共享同一 CodeSandbox）：
    - write_file   : 全量写入文件，自动同步索引
    - patch_symbol : 按符号名精准替换类 / 函数定义
    - replace_lines: 按行号范围精准替换代码段

    运行/诊断工具（来自 SandboxDiagnosticsTool，与读写工具共享同一 CodeSandbox）：
    - run_python      : 运行 Python 文件或模块
    - check_syntax    : 显式检查 Python 语法/缩进错误
    - check_imports   : 静态分析 Python 导入解析问题
    - diagnose_python : 汇总执行语法与导入诊断

    参数
    ----
    sandbox : 可传入已有 SandboxTool 实例以跨 bridge 共享；
              None 时自动创建新实例。

    返回
    ----
    (bridge, sandbox_tool) — bridge 供注册到 ToolBridge；
                             sandbox_tool 供调用方持有以便后续共享。
    """
    # 读工具、写工具、诊断工具必须共享同一个 sandbox，否则写入后的索引和诊断会脱节。
    tool = sandbox or build_sandbox_tool()
    write_tool = build_sandbox_write_tool(tool)
    diagnostic_tool = build_sandbox_diagnostics_tool(tool)

    bridge = ToolBridge()
    for name in _SANDBOX_TOOL_NAMES:
        bridge.register_tool(name, getattr(tool, name))
    for name in _SANDBOX_WRITE_TOOL_NAMES:
        bridge.register_tool(name, getattr(write_tool, name))
    for name in _SANDBOX_DIAGNOSTIC_TOOL_NAMES:
        bridge.register_tool(name, getattr(diagnostic_tool, name))
    return bridge, tool
