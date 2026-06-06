from __future__ import annotations

import subprocess
import sys


def _run(cmd: list[str], step_text: str) -> None:
    # 安装脚本只做环境准备，不参与运行时业务逻辑。
    print(step_text, flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    # 使用当前 Python 解释器安装依赖，避免装到系统里另一个 Python 环境。
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
