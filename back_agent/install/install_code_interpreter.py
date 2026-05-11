from __future__ import annotations

import subprocess
import sys


def _run(cmd: list[str], step_text: str) -> None:
    print(step_text, flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    python_exe = sys.executable
    _run([python_exe, "--version"], "[1/3] 检查 Python 可用性...")
    _run([python_exe, "-m", "pip", "install", "--upgrade", "pip"], "[2/3] 升级 pip...")
    _run(
        [python_exe, "-m", "pip", "install", "--upgrade", "openai"],
        "[3/3] 安装 Code Interpreter 依赖...",
    )
    print("安装完成。已安装依赖: openai", flush=True)


if __name__ == "__main__":
    main()
