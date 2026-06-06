from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence


ToolFunc = Callable[..., Any]


@dataclass(frozen=True)
class ParsedToolCall:
    """从 agent 输出中提取的单次工具调用。"""

    tool_name: str
    args: List[Any]
    kwargs: Dict[str, Any]
    raw: str


class ToolBridge:
    """
    解析并执行 agent 文本中的 tool_call 调用。

    约定:
    - agent 输出采用函数调用风格。
    - 推荐格式:
      1) tool_call("tool_name", arg1, x=1)
      2) tool_call(tool_name="tool_name", x="abc")
      3) tool_call(name="tool_name", x="abc")
    """

    _CALL_PATTERN = re.compile(r"tool_call\s*\(")

    def __init__(self) -> None:
        # 工具名 -> Python callable；ReactAgent 只输出文本，真正执行在这里发生。
        self._tools: Dict[str, ToolFunc] = {}

    def register_tool(self, name: str, func: ToolFunc) -> None:
        """注册一个工具函数。"""
        tool_name = (name or "").strip()
        if not tool_name:
            raise ValueError("工具名不能为空。")
        if not callable(func):
            raise TypeError(f"工具 {tool_name} 不是可调用对象。")
        self._tools[tool_name] = func

    def has_tool(self, name: str) -> bool:
        return (name or "").strip() in self._tools

    def contains_tool_call(self, text: str) -> bool:
        """判断文本中是否存在 tool_call( 模式（不论是否能成功解析）。"""
        return bool(self._CALL_PATTERN.search(text or ""))

    def parse_tool_calls(self, text: str) -> List[ParsedToolCall]:
        """从任意文本中提取全部 tool_call(...)。"""
        # 先按括号/字符串边界切片，再用 AST 解析，避免正则直接解析嵌套字符串。
        content = text or ""
        spans = self._extract_call_spans(content)
        calls: List[ParsedToolCall] = []
        for full_call in spans:
            try:
                parsed = self._parse_single_call(full_call)
                calls.append(parsed)
            except ValueError:
                # 单条 span 解析失败（如截断的三重引号）时跳过，不影响其他 span
                pass
        return calls

    def execute_call(self, call: ParsedToolCall) -> Any:
        """执行单个已解析的工具调用。"""
        if call.tool_name not in self._tools:
            raise KeyError(f"未注册的工具: {call.tool_name}")
        return self._tools[call.tool_name](*call.args, **call.kwargs)

    def execute_from_text(
        self,
        text: str,
        *,
        execute_all: bool = False,
    ) -> Any:
        """
        从文本中解析并执行工具调用。

        - execute_all=False: 仅执行第一条 tool_call
        - execute_all=True: 依次执行全部 tool_call，返回结果列表
        """
        calls = self.parse_tool_calls(text)
        if not calls:
            raise ValueError("未在文本中找到 tool_call(...)。")

        if execute_all:
            return [self.execute_call(c) for c in calls]
        return self.execute_call(calls[0])

    def _extract_call_spans(self, text: str) -> List[str]:
        """提取完整的 tool_call(...) 片段，处理括号与字符串。"""
        # 这里不执行工具，只负责找出语法上完整的 tool_call(...) 文本片段。
        matches = list(self._CALL_PATTERN.finditer(text))
        if not matches:
            return []

        spans: List[str] = []
        for match in matches:
            start = match.start()
            open_idx = text.find("(", match.start())
            if open_idx < 0:
                continue
            end = self._find_matching_paren(text, open_idx)
            if end < 0:
                continue
            spans.append(text[start : end + 1])
        return spans

    @staticmethod
    def _find_matching_paren(text: str, open_idx: int) -> int:
        """
        找到与 open_idx 处 '(' 匹配的 ')' 的位置。

        正确处理单引号、双引号以及三重引号（'''/\"\"\"）字符串的任意嵌套，
        字符串内部的括号不计入深度。

        核心改进：使用引号栈（quote_stack）替代单个 in_quote 变量。
        当处于三重引号字符串内（如 \"\"\"...\"\"\"）时，若遇到另一种
        三重引号（如 '''...'''），将其压栈追踪，内层结束后弹栈继续
        追踪外层。这样 \"\"\" 出现在 '''...''' 内部时不会被误判为
        外层 \"\"\" 的结束，反之亦然。

        支持的嵌套场景示例：
          tool_call("write_file", path="tmp/demo.py", content=\"\"\"
              code = '''
                  def f():
                      \"\"\"docstring inside inner triple-single quote\"\"\"
              '''
          \"\"\")
        """
        depth = 0
        # quote_stack: 引号栈，每个元素为当前层字符串的起始引号（长度 1 或 3）。
        # 栈顶（最后一个元素）为当前最内层字符串的引号类型；空栈表示不在任何字符串内。
        quote_stack: list = []
        escaped = False

        i = open_idx
        while i < len(text):
            ch = text[i]

            if quote_stack:
                # —— 处于某层字符串内部 ——
                current_quote = quote_stack[-1]

                if escaped:
                    escaped = False
                    i += 1
                    continue
                if ch == "\\":
                    escaped = True
                    i += 1
                    continue

                if len(current_quote) == 3:
                    # 当前层为三重引号字符串
                    # 先检测是否出现与当前层 不同类型 的三重引号 → 压入新层
                    other_triple = "'''" if current_quote[0] == '"' else '"""'
                    if text[i : i + 3] == other_triple:
                        quote_stack.append(other_triple)
                        i += 3
                        continue
                    # 再检测当前层结束（三个相同字符）
                    if text[i : i + 3] == current_quote:
                        quote_stack.pop()
                        i += 3
                        continue
                    i += 1
                    continue
                else:
                    # 当前层为单字符引号字符串：遇到相同字符退出
                    if ch == current_quote:
                        quote_stack.pop()
                    i += 1
                    continue

            # —— 不在任何字符串内部 ——
            # 先检测三重引号（避免把 """ 的第一个 " 误当单字符引号处理）
            if ch in ('"', "'") and text[i : i + 3] in ('"""', "'''"):
                quote_stack.append(text[i : i + 3])
                i += 3
                continue
            if ch in ('"', "'"):
                quote_stack.append(ch)
                i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
            i += 1

        return -1

    def _parse_single_call(self, raw_call: str) -> ParsedToolCall:
        """
        解析单条 tool_call(...)。

        用 Python AST 做语法解析，兼容 Python 字面量参数。
        """
        try:
            # ast.parse 只接受合法 Python 表达式，因此 tool_call 参数要像 Python 字面量。
            expr = ast.parse(raw_call, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"tool_call 语法错误: {raw_call}") from exc

        if not isinstance(expr.body, ast.Call):
            raise ValueError(f"不是函数调用表达式: {raw_call}")
        call_node = expr.body

        if not isinstance(call_node.func, ast.Name) or call_node.func.id != "tool_call":
            raise ValueError(f"不支持的调用形式: {raw_call}")

        args = [self._literal_or_source(node, raw_call) for node in call_node.args]
        kwargs = {
            (kw.arg or ""): self._literal_or_source(kw.value, raw_call)
            for kw in call_node.keywords
            if kw.arg
        }

        tool_name = self._resolve_tool_name(args=args, kwargs=kwargs)
        cleaned_args = self._strip_tool_name_from_args(args=args, kwargs=kwargs)
        cleaned_kwargs = dict(kwargs)
        cleaned_kwargs.pop("tool_name", None)
        cleaned_kwargs.pop("name", None)

        return ParsedToolCall(
            tool_name=tool_name,
            args=cleaned_args,
            kwargs=cleaned_kwargs,
            raw=raw_call,
        )

    @staticmethod
    def _literal_or_source(node: ast.AST, source: str) -> Any:
        try:
            return ast.literal_eval(node)
        except Exception:
            # 允许出现变量名等非字面量，把原始片段透传给工具自行处理。
            segment = ast.get_source_segment(source, node)
            if segment is None:
                return None
            return segment.strip()

    @staticmethod
    def _resolve_tool_name(args: Sequence[Any], kwargs: Dict[str, Any]) -> str:
        # 支持三种工具名写法：第一个位置参数、tool_name=、name=。
        if "tool_name" in kwargs and str(kwargs["tool_name"]).strip():
            return str(kwargs["tool_name"]).strip()
        if "name" in kwargs and str(kwargs["name"]).strip():
            return str(kwargs["name"]).strip()
        if args and str(args[0]).strip():
            return str(args[0]).strip()
        raise ValueError("tool_call 缺少工具名，请使用第一个位置参数或 tool_name/name 关键字。")

    @staticmethod
    def _strip_tool_name_from_args(args: Sequence[Any], kwargs: Dict[str, Any]) -> List[Any]:
        if "tool_name" in kwargs or "name" in kwargs:
            return list(args)
        if not args:
            return []
        return list(args[1:])


