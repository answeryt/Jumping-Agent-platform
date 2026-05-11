from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.base_agent import PromptLoader
from agent.react import ReactAgent, ReactAgentConfig


class _TestableReactAgent(ReactAgent):
    """为测试提供 run 实现，避免抽象类实例化失败。"""

    def run(self, user_input: str, **kwargs) -> str:
        return f"ok:{user_input}"


def test_react_agent_is_abstract_and_cannot_be_instantiated():
    """当前 ReactAgent 未实现 run，直接实例化应失败。"""
    with pytest.raises(TypeError):
        ReactAgent()


def test_react_agent_can_run_with_test_subclass_and_existing_prompt():
    """通过测试子类验证 ReactAgent 基础链路可正常运行。"""
    prompt_loader = PromptLoader(prompt_dir=PROJECT_ROOT / "prompt")
    config = ReactAgentConfig(prompt_file="react_agent_prompt.md")
    agent = _TestableReactAgent(config=config, prompt_loader=prompt_loader)

    loaded_prompt = agent.load_prompt()

    assert agent.agent_type == "react"
    assert isinstance(loaded_prompt, str) and loaded_prompt.strip()
    assert agent.run("ping") == "ok:ping"


def test_default_prompt_config_likely_not_runnable_with_current_files():
    """
    用当前仓库默认值做烟雾检测：
    ReactAgentConfig 默认 prompt_file 是 react_agent.md，
    但当前仓库里常见文件名为 react_agent_prompt.md（若未对齐会抛 FileNotFoundError）。
    """
    prompt_loader = PromptLoader(prompt_dir=PROJECT_ROOT / "prompt")
    config = ReactAgentConfig()

    with pytest.raises(FileNotFoundError):
        prompt_loader.load(config.prompt_file)


def main() -> int:
    """允许直接运行本文件执行测试。"""
    return pytest.main(
        [
            "-p",
            "no:cacheprovider",
            str(Path(__file__).resolve()),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
