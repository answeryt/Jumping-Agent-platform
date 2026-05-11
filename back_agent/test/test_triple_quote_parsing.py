"""
快速验证 _find_matching_paren 的三重引号兜底逻辑修复。
不依赖网络，直接在本地运行即可。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.tool_bridge import ToolBridge


def main() -> None:
    bridge = ToolBridge()
    bridge.register_tool("demo", lambda **kw: kw)

    # 测试1：三重引号中含有多个 print("...") 括号
    text1 = (
        'tool_call("demo", code="""'
        "\nprint(\"hello\")"
        "\nprint(\"=\" * 60)"
        "\nfor i in range(10):"
        "\n    print(i)"
        '\n""")'
    )
    calls1 = bridge.parse_tool_calls(text1)
    assert len(calls1) == 1, f"期望1个调用，实际 {len(calls1)}"
    code_val = calls1[0].kwargs.get("code", "")
    assert "print" in code_val, f"未能提取 code 参数，实际 kwargs={calls1[0].kwargs}"
    print("[OK] Test1: triple-double-quote brackets parsed correctly")

    # 测试2：stop 未触发，LLM 写了 Observation，仍能解析 tool_call
    text2 = (
        "Thought: 我需要执行代码\n"
        'Action: tool_call("demo", code="""'
        "\nx = 1 + 1\nprint(x)\n"
        '""")\n'
        "Observation: 2\n"
        "Thought: 完成\n"
        "Final Answer: 答案是2"
    )
    calls2 = bridge.parse_tool_calls(text2)
    assert len(calls2) == 1, f"期望1个调用，实际 {len(calls2)}"
    print("[OK] Test2: full ReAct text with Observation still parses tool_call")

    # 测试3：三重单引号
    text3 = "tool_call('demo', instruction='run', code='''print(42)''')"
    calls3 = bridge.parse_tool_calls(text3)
    assert len(calls3) == 1, f"期望1个调用，实际 {len(calls3)}"
    print("[OK] Test3: triple-single-quote parsed correctly")

    # 测试4：代码中含有嵌套函数调用 func(arg1, func2(x))
    text4 = (
        'tool_call("demo", code="""'
        "\nresult = max(min(10, 20), abs(-5))"
        "\nprint(result)"
        '\n""")'
    )
    calls4 = bridge.parse_tool_calls(text4)
    assert len(calls4) == 1, f"期望1个调用，实际 {len(calls4)}"
    print("[OK] Test4: nested function calls inside triple-quote parsed correctly")

    # 测试5：恶意/截断 span（兜底跳过而非崩溃）
    bad_text = 'tool_call("demo", code="""print("unterminated'
    calls5 = bridge.parse_tool_calls(bad_text)
    assert len(calls5) == 0, f"截断 span 应被跳过，实际 {len(calls5)}"
    print("[OK] Test5: truncated span safely skipped, no crash")

    print("\nAll 5 tests passed.")


if __name__ == "__main__":
    main()
