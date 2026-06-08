from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ExecResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class ExecutorProtocol(Protocol):
    def run(self, command: list, workdir: str = "/workspace", timeout: int = 30) -> ExecResult:
        ...

    def write_file(self, container_path: str, content: str) -> ExecResult:
        ...


class LocalWorkspaceExecutor:
    """Small local replacement for the old container-backed project writer."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def run(self, command: list, workdir: str = "/workspace", timeout: int = 30) -> ExecResult:
        del workdir, timeout
        if command[:2] == ["test", "-f"] and len(command) >= 3:
            return ExecResult(returncode=0 if self._resolve(command[2]).is_file() else 1)
        if command[:2] == ["mkdir", "-p"] and len(command) >= 3:
            self._resolve(command[2]).mkdir(parents=True, exist_ok=True)
            return ExecResult()
        return ExecResult(stderr=f"unsupported local command: {command}", returncode=1)

    def write_file(self, container_path: str, content: str) -> ExecResult:
        path = self._resolve(container_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ExecResult()

    def _resolve(self, path: str) -> Path:
        normalized = str(path).replace("\\", "/")
        if normalized == "/workspace":
            return self.workspace_root
        if normalized.startswith("/workspace/"):
            return self.workspace_root / normalized.removeprefix("/workspace/")
        return Path(normalized)
