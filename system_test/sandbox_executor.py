"""
sandbox_executor.py  —  system_test 目录专用 shim

为什么需要这个文件
──────────────────────────────────────────────────────────────────────
agent_builder/agent_create/create_agent.py 在模块顶层执行：

    SANDBOX_ROOT = PROJECT_ROOT / "sandbox"
    sys.path.insert(0, str(SANDBOX_ROOT))
    from sandbox_executor import SandboxExecutor

当通过 importlib.util.spec_from_file_location + exec_module 动态加载
上述模块时，sys.path.insert 有时不能被 Python 导入机制及时感知，
导致 ModuleNotFoundError。

system_test/ 作为测试脚本的入口目录，始终位于 sys.path[0]，
因此在此放置本文件可作为可靠的 fallback。

接口与 sandbox/sandbox_executor.py 完全一致：
  - 测试中由 LocalExecutor 替代，SandboxExecutor 不会被实例化；
  - 若因其他路径真正需要实例化，本实现与原版行为相同。
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

# /workspace/ → 本机目标目录（与 sandbox/sandbox_executor.py 保持一致）
WORKSPACE_ROOT: Path = (
    Path(__file__).resolve().parent / "agent_test"
)

CONTAINER_PREFIX = "/workspace/"


@dataclass
class CommandResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class WriteResult:
    ok: bool = True
    stderr: str = ""


class SandboxExecutor:
    """
    本地文件系统沙盒执行器（system_test shim）。

    将容器路径 /workspace/... 映射到 WORKSPACE_ROOT/...，
    通过 pathlib 完成 mkdir / test / write 操作，
    完全不依赖 Docker 或真实沙盒环境。
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self._root = workspace_root or WORKSPACE_ROOT
        self._root.mkdir(parents=True, exist_ok=True)

    def _to_local(self, container_path: str) -> Path:
        """将 /workspace/... 转为本机绝对路径。"""
        path = container_path
        if path.startswith(CONTAINER_PREFIX):
            relative = path[len(CONTAINER_PREFIX):]
        elif path.startswith("/workspace"):
            relative = path[len("/workspace"):]
            if relative.startswith("/"):
                relative = relative[1:]
        else:
            relative = path.lstrip("/")
        return (self._root / relative).resolve()

    def run(self, cmd: Sequence[str]) -> CommandResult:
        """
        模拟容器内 shell 命令执行。
        支持：mkdir -p、test -f、test -d、echo、ls。
        """
        if not cmd:
            return CommandResult(returncode=1, stderr="空命令")

        program = cmd[0]
        args = list(cmd[1:])

        if program == "mkdir":
            paths = [a for a in args if not a.startswith("-")]
            for p in paths:
                local = self._to_local(p)
                try:
                    local.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    return CommandResult(returncode=1, stderr=str(exc))
            return CommandResult(returncode=0)

        if program == "test":
            flag = args[0] if args else ""
            target = args[1] if len(args) > 1 else ""
            local = self._to_local(target)
            if flag == "-f":
                exists = local.is_file()
            elif flag == "-d":
                exists = local.is_dir()
            else:
                exists = local.exists()
            return CommandResult(returncode=0 if exists else 1)

        if program == "echo":
            return CommandResult(returncode=0, stdout=" ".join(args))

        if program == "ls":
            target = args[-1] if args and not args[-1].startswith("-") else "."
            local = self._to_local(target)
            if local.is_dir():
                entries = "\n".join(e.name for e in local.iterdir())
                return CommandResult(returncode=0, stdout=entries)
            return CommandResult(returncode=1, stderr=f"不是目录: {local}")

        return CommandResult(
            returncode=127,
            stderr=f"SandboxExecutor: 未知命令 '{program}'",
        )

    def write_file(self, container_path: str, content: str) -> WriteResult:
        """将 content 写入映射后的本机路径，自动创建父目录。"""
        local = self._to_local(container_path)
        try:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(content, encoding="utf-8")
            return WriteResult(ok=True)
        except Exception as exc:
            return WriteResult(ok=False, stderr=str(exc))

    def read_file(self, container_path: str) -> str:
        """读取映射路径的文件内容。"""
        local = self._to_local(container_path)
        if not local.is_file():
            raise FileNotFoundError(f"文件不存在: {local}")
        return local.read_text(encoding="utf-8")

    @property
    def workspace_root(self) -> Path:
        return self._root
