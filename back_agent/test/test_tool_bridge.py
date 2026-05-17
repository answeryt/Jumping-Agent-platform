from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.tool_bridge import ToolBridge  # noqa: E402
from tools.shell_tool_adapter import build_sandbox_bridge  # noqa: E402


class TestToolBridgeParsing:
    def test_parse_positional_tool_name(self):
        text = 'tool_call("find", "TODO")'
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "find"
        assert calls[0].args == ["TODO"]

    def test_parse_tool_name_kwarg(self):
        text = 'tool_call(tool_name="get", target="tools/sandbox_tools.py")'
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "get"
        assert calls[0].kwargs["target"] == "tools/sandbox_tools.py"

    def test_parse_name_kwarg(self):
        text = 'tool_call(name="config")'
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "config"

    def test_parse_embedded_in_react_text(self):
        text = (
            "Thought: 需要搜索\n"
            'Action: tool_call("find", "TODO")\n'
            "Observation: (pending)"
        )
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "find"

    def test_parse_multiple_calls(self):
        text = (
            'tool_call("find", "TODO")\n'
            'tool_call("get", "tools/sandbox_tools.py")\n'
        )
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 2
        assert calls[0].tool_name == "find"
        assert calls[1].tool_name == "get"

    def test_parse_returns_empty_when_no_call(self):
        assert ToolBridge().parse_tool_calls("Final Answer: done.") == []

    def test_parse_multiline_string_arg(self):
        text = 'tool_call("write_file", path="tmp/demo.py", content="""print(1)\nprint(2)""")'
        calls = ToolBridge().parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool_name == "write_file"

    def test_parse_positional_args_stripped_of_tool_name(self):
        text = 'tool_call("replace_lines", "config/settings.py", 1, 2, "x = 1")'
        calls = ToolBridge().parse_tool_calls(text)
        assert calls[0].args == ["config/settings.py", 1, 2, "x = 1"]
        assert calls[0].kwargs == {}


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
            ToolBridge().register_tool("x", "not_a_function")  # type: ignore[arg-type]


class TestBuildSandboxBridge:
    def test_returns_tool_bridge(self):
        bridge, _ = build_sandbox_bridge()
        assert isinstance(bridge, ToolBridge)

    def test_has_all_expected_tools(self):
        bridge, _ = build_sandbox_bridge()
        for name in (
            "load_project",
            "tree",
            "find",
            "get",
            "config",
            "write_file",
            "patch_symbol",
            "replace_lines",
        ):
            assert bridge.has_tool(name), f"缺少工具: {name}"


def main() -> int:
    return pytest.main(
        ["-p", "no:cacheprovider", str(Path(__file__).resolve()), "-v"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
