from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ShellResult:
    stdout: str
    stderr: str
    returncode: int
    ok: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ShellTool:
    """Compatibility wrapper for older local shell/code tool tests."""

    def __init__(
        self,
        default_cwd: Optional[str | Path] = None,
        timeout: int = 30,
    ) -> None:
        self.default_cwd = str(Path(default_cwd).resolve()) if default_cwd else None
        self.timeout = int(timeout)

    def _run_command(
        self,
        command: list[str] | str,
        *,
        cwd: Optional[str | Path] = None,
        timeout: Optional[int] = None,
        shell: bool = False,
    ) -> ShellResult:
        working_dir = str(Path(cwd).resolve()) if cwd else self.default_cwd
        try:
            completed = subprocess.run(
                command,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                shell=shell,
                encoding="utf-8",
                errors="replace",
            )
            return ShellResult(
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
                ok=completed.returncode == 0,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            timeout_text = f"[TIMEOUT] command exceeded {timeout or self.timeout} seconds"
            stderr = f"{stderr}\n{timeout_text}".strip()
            return ShellResult(stdout=stdout, stderr=stderr, returncode=124, ok=False)
        except Exception as exc:
            return ShellResult(stdout="", stderr=str(exc), returncode=1, ok=False)

    def run(
        self,
        command: str,
        cwd: Optional[str | Path] = None,
        timeout: Optional[int] = None,
    ) -> ShellResult:
        return self._run_command(command, cwd=cwd, timeout=timeout, shell=True)

    def bash(
        self,
        command: str,
        cwd: Optional[str | Path] = None,
        timeout: Optional[int] = None,
    ) -> ShellResult:
        return self.run(command, cwd=cwd, timeout=timeout)

    def exec_script(
        self,
        script: str,
        cwd: Optional[str | Path] = None,
        timeout: Optional[int] = None,
    ) -> ShellResult:
        return self.python_batch(script, cwd=cwd, timeout=timeout)

    def python_batch(
        self,
        script: str,
        cwd: Optional[str | Path] = None,
        timeout: Optional[int] = None,
    ) -> ShellResult:
        return self._run_command(
            [sys.executable, "-c", script],
            cwd=cwd,
            timeout=timeout,
            shell=False,
        )

    def sed(
        self,
        path: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> ShellResult:
        target = Path(path)
        if not target.is_absolute() and self.default_cwd:
            target = Path(self.default_cwd) / target
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
            start = max(1, int(start_line))
            end = int(end_line) if end_line is not None else len(lines)
            snippet = "\n".join(
                f"{line_no}: {line}"
                for line_no, line in enumerate(lines[start - 1 : end], start=start)
            )
            return ShellResult(stdout=snippet, stderr="", returncode=0, ok=True)
        except Exception as exc:
            return ShellResult(stdout="", stderr=str(exc), returncode=1, ok=False)

    def perl_replace(
        self,
        path: str,
        pattern: str,
        replacement: str,
    ) -> ShellResult:
        target = Path(path)
        if not target.is_absolute() and self.default_cwd:
            target = Path(self.default_cwd) / target
        try:
            content = target.read_text(encoding="utf-8")
            new_content, count = re.subn(pattern, replacement, content)
            target.write_text(new_content, encoding="utf-8")
            return ShellResult(stdout=f"replacements={count}", stderr="", returncode=0, ok=True)
        except Exception as exc:
            return ShellResult(stdout="", stderr=str(exc), returncode=1, ok=False)

    def git_diff(self, cwd: Optional[str | Path] = None) -> ShellResult:
        return self._run_command(["git", "diff"], cwd=cwd, shell=False)

    def grep(self, pattern: str, path: str = ".") -> ShellResult:
        root = Path(path)
        if not root.is_absolute() and self.default_cwd:
            root = Path(self.default_cwd) / root
        matches: list[str] = []
        try:
            files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
            for file_path in files:
                try:
                    for line_no, line in enumerate(
                        file_path.read_text(encoding="utf-8", errors="replace").splitlines(),
                        start=1,
                    ):
                        if pattern in line:
                            matches.append(f"{file_path}:{line_no}:{line}")
                except Exception:
                    continue
            return ShellResult(stdout="\n".join(matches), stderr="", returncode=0, ok=True)
        except Exception as exc:
            return ShellResult(stdout="", stderr=str(exc), returncode=1, ok=False)

    def ripgrep(self, pattern: str, path: str = ".") -> ShellResult:
        rg_result = self._run_command(["rg", pattern, path], shell=False)
        if rg_result.returncode != 1 or rg_result.stdout or rg_result.stderr:
            return rg_result
        return self.grep(pattern, path)
