from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.code_tools import ShellResult, ShellTool  # noqa: E402
from tools.shell_tool_adapter import ShellToolAdapter, build_shell_bridge  # noqa: E402
from tools.tool_bridge import ToolBridge  # noqa: E402


def _fake_result(stdout: str = "ok", stderr: str = "", returncode: int = 0) -> ShellResult:
    return ShellResult(
        cmd="test", stdout=stdout, stderr=stderr, returncode=returncode, cwd="/"
    )


# ------------------------------------------------------------------
# ToolBridge — 解析测试
# ------------------------------------------------------------------

class TestToolBridgeParsing:
    def test_parse_positional_tool_name(self):
        text = 'tool_call("bash", script="echo hello")'
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "bash"
        assert calls[0].kwargs["script"] == "echo hello"

    def test_parse_tool_name_kwarg(self):
        text = 'tool_call(tool_name="ripgrep", pattern="TODO", path="src/")'
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "ripgrep"
        assert calls[0].kwargs["pattern"] == "TODO"

    def test_parse_name_kwarg(self):
        text = 'tool_call(name="git_diff", staged=True)'
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "git_diff"

    def test_parse_embedded_in_react_text(self):
        text = (
            "Thought: 需要搜索\n"
            'Action: tool_call("ripgrep", pattern="TODO", path="src/")\n'
            "Observation: (pending)"
        )
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "ripgrep"

    def test_parse_multiple_calls(self):
        text = (
            'tool_call("ripgrep", pattern="TODO")\n'
            'tool_call("bash", script="ls")\n'
        )
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 2
        assert calls[0].tool_name == "ripgrep"
        assert calls[1].tool_name == "bash"

    def test_parse_returns_empty_when_no_call(self):
        assert ToolBridge().parse_tool_calls("Final Answer: done.") == []

    def test_parse_multiline_string_arg(self):
        text = 'tool_call("python_batch", script="""print(1)\nprint(2)""")'
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "python_batch"

    def test_parse_positional_args_stripped_of_tool_name(self):
        text = 'tool_call("run", "ls -la", cwd="/repo")'
        calls = ToolBridge().parse_tool_calls(text)
        assert calls[0].args == ["ls -la"]
        assert calls[0].kwargs == {"cwd": "/repo"}


# ------------------------------------------------------------------
# ToolBridge — 注册与执行
# ------------------------------------------------------------------

class TestToolBridgeRegisterAndExecute:
    def test_register_and_execute(self):
        bridge = ToolBridge()
        bridge.register_tool("echo", lambda msg="": {"echo": msg})
        result = bridge.execute_from_text('tool_call("echo", msg="hi")')
        assert result == {"echo": "hi"}

    def test_has_tool_after_register(self):
        bridge = ToolBridge()
        bridge.register_tool("noop", lambda: None)
        assert bridge.has_tool("noop") is True
        assert bridge.has_tool("missing") is False

    def test_execute_unknown_tool_raises_key_error(self):
        with pytest.raises(KeyError, match="未注册的工具"):
            ToolBridge().execute_from_text('tool_call("unknown_tool")')

    def test_execute_all_returns_list(self):
        bridge = ToolBridge()
        bridge.register_tool("echo", lambda msg="": msg)
        text = 'tool_call("echo", msg="a")\ntool_call("echo", msg="b")'
        results = bridge.execute_from_text(text, execute_all=True)
        assert results == ["a", "b"]

    def test_execute_from_text_no_call_raises(self):
        with pytest.raises(ValueError, match="未在文本中找到"):
            ToolBridge().execute_from_text("no tool call here")

    def test_register_empty_name_raises(self):
        with pytest.raises(ValueError):
            ToolBridge().register_tool("", lambda: None)

    def test_register_non_callable_raises(self):
        with pytest.raises(TypeError):
            ToolBridge().register_tool("x", "not_a_function")  # type: ignore


# ------------------------------------------------------------------
# ShellToolAdapter
# ------------------------------------------------------------------

class TestShellToolAdapter:
    def test_adapter_wraps_method_and_returns_dict(self):
        tool = MagicMock(spec=ShellTool)
        tool.bash.return_value = _fake_result(stdout="hi")
        adapter = ShellToolAdapter(tool, "bash")
        result = adapter(script="echo hi")
        assert isinstance(result, dict)
        assert result["stdout"] == "hi"
        assert result["returncode"] == 0
        assert result["ok"] is True
        assert "stderr" in result

    def test_adapter_raises_on_nonexistent_method(self):
        with pytest.raises(AttributeError):
            ShellToolAdapter(ShellTool(), "nonexistent_method")

    def test_adapter_passes_positional_args(self):
        tool = MagicMock(spec=ShellTool)
        tool.run.return_value = _fake_result()
        ShellToolAdapter(tool, "run")("ls -la")
        tool.run.assert_called_once_with("ls -la")

    def test_adapter_passes_kwargs(self):
        tool = MagicMock(spec=ShellTool)
        tool.git_diff.return_value = _fake_result()
        ShellToolAdapter(tool, "git_diff")(staged=True, cwd="/repo")
        tool.git_diff.assert_called_once_with(staged=True, cwd="/repo")

    def test_adapter_repr_contains_method_name(self):
        adapter = ShellToolAdapter(ShellTool(), "bash")
        assert "bash" in repr(adapter)

    def test_adapter_error_result_propagated(self):
        tool = MagicMock(spec=ShellTool)
        tool.run.return_value = _fake_result(stderr="fail", returncode=1)
        result = ShellToolAdapter(tool, "run")("bad_cmd")
        assert result["ok"] is False
        assert result["returncode"] == 1
        assert result["stderr"] == "fail"


# ------------------------------------------------------------------
# build_shell_bridge
# ------------------------------------------------------------------

class TestBuildShellBridge:
    def test_returns_tool_bridge(self):
        assert isinstance(build_shell_bridge(), ToolBridge)

    def test_has_all_expected_tools(self):
        bridge = build_shell_bridge()
        for name in (
            "run", "bash", "exec_script", "sed", "perl_replace",
            "python_batch", "git_diff", "grep", "ripgrep",
        ):
            assert bridge.has_tool(name), f"缺少工具: {name}"

    def test_python_batch_via_bridge(self):
        bridge = build_shell_bridge()
        result = bridge.execute_from_text(
            'tool_call("python_batch", script="print(\'hello bridge\')")'
        )
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert "hello bridge" in result["stdout"]

    def test_exec_script_via_bridge(self):
        bridge = build_shell_bridge()
        result = bridge.execute_from_text(
            'tool_call("exec_script", script="print(1+1)", lang="python")'
        )
        assert result["ok"] is True
        assert "2" in result["stdout"]

    def test_bridge_execute_returns_serializable_dict(self):
        bridge = build_shell_bridge()
        result = bridge.execute_from_text(
            'tool_call("bash", script="echo serializable")'
        )
        assert isinstance(result, dict)
        for key in ("stdout", "stderr", "returncode", "ok"):
            assert key in result


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def main() -> int:
    return pytest.main(
        ["-p", "no:cacheprovider", str(Path(__file__).resolve()), "-v"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
