from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List


ToolFunc = Callable[..., Any]


@dataclass(frozen=True)
class ParsedToolCall:
    """A parsed ``tool_call(...)`` expression emitted by a text ReAct agent."""

    tool_name: str
    args: List[Any]
    kwargs: Dict[str, Any]
    raw: str


@dataclass(frozen=True)
class ParsedToolRequest:
    """A parsed ``tool_request(...)`` expression emitted by a text ReAct agent."""

    request_name: str
    args: List[Any]
    kwargs: Dict[str, Any]
    raw: str


class ToolBridge:
    """Parse and execute Python-literal ``tool_call`` snippets from model text."""

    _CALL_PATTERN = re.compile(r"tool_call\s*\(")
    _REQUEST_PATTERN = re.compile(r"tool_request\s*\(")

    def __init__(self) -> None:
        self._tools: Dict[str, ToolFunc] = {}

    def register_tool(self, name: str, func: ToolFunc) -> None:
        tool_name = (name or "").strip()
        if not tool_name:
            raise ValueError("工具名不能为空。")
        if not callable(func):
            raise TypeError(f"工具 {tool_name} 不是可调用对象。")
        self._tools[tool_name] = func

    def has_tool(self, name: str) -> bool:
        return (name or "").strip() in self._tools

    def contains_tool_call(self, text: str) -> bool:
        return bool(self._CALL_PATTERN.search(text or ""))

    def contains_tool_request(self, text: str) -> bool:
        return bool(self._REQUEST_PATTERN.search(text or ""))

    def parse_tool_calls(self, text: str) -> List[ParsedToolCall]:
        calls: List[ParsedToolCall] = []
        for raw_call in self._extract_call_spans(text or ""):
            try:
                calls.append(self._parse_single_call(raw_call))
            except ValueError:
                continue
        return calls

    def parse_tool_requests(self, text: str) -> List[ParsedToolRequest]:
        requests: List[ParsedToolRequest] = []
        for raw_request in self._extract_request_spans(text or ""):
            try:
                requests.append(self._parse_single_request(raw_request))
            except ValueError:
                continue
        return requests

    def execute_call(self, call: ParsedToolCall) -> Any:
        if call.tool_name not in self._tools:
            raise KeyError(f"未注册的工具: {call.tool_name}")
        return self._tools[call.tool_name](*call.args, **call.kwargs)

    def execute_from_text(self, text: str, *, execute_all: bool = False) -> Any:
        calls = self.parse_tool_calls(text)
        if not calls:
            raise ValueError("未在文本中找到 tool_call(...)。")
        if execute_all:
            return [self.execute_call(call) for call in calls]
        return self.execute_call(calls[0])

    def _extract_call_spans(self, text: str) -> List[str]:
        return self._extract_spans(text, self._CALL_PATTERN)

    def _extract_request_spans(self, text: str) -> List[str]:
        return self._extract_spans(text, self._REQUEST_PATTERN)

    def _extract_spans(self, text: str, pattern: re.Pattern[str]) -> List[str]:
        spans: List[str] = []
        for match in pattern.finditer(text):
            open_idx = text.find("(", match.start())
            if open_idx < 0:
                continue
            end_idx = self._find_matching_paren(text, open_idx)
            if end_idx >= 0:
                spans.append(text[match.start() : end_idx + 1])
        return spans

    @staticmethod
    def _find_matching_paren(text: str, open_idx: int) -> int:
        depth = 0
        quote_stack: List[str] = []
        escaped = False
        i = open_idx
        while i < len(text):
            ch = text[i]
            if quote_stack:
                current = quote_stack[-1]
                if escaped:
                    escaped = False
                    i += 1
                    continue
                if ch == "\\":
                    escaped = True
                    i += 1
                    continue
                if len(current) == 3:
                    other = "'''" if current[0] == '"' else '"""'
                    if text[i : i + 3] == other:
                        quote_stack.append(other)
                        i += 3
                        continue
                    if text[i : i + 3] == current:
                        quote_stack.pop()
                        i += 3
                        continue
                    i += 1
                    continue
                if ch == current:
                    quote_stack.pop()
                i += 1
                continue

            if ch in ("'", '"') and text[i : i + 3] in ("'''", '"""'):
                quote_stack.append(text[i : i + 3])
                i += 3
                continue
            if ch in ("'", '"'):
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
        try:
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
        }
        tool_name = self._resolve_tool_name(args, kwargs)
        return ParsedToolCall(tool_name=tool_name, args=args, kwargs=kwargs, raw=raw_call)

    def _parse_single_request(self, raw_request: str) -> ParsedToolRequest:
        try:
            expr = ast.parse(raw_request, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"tool_request 语法错误: {raw_request}") from exc
        if not isinstance(expr.body, ast.Call):
            raise ValueError(f"不是函数调用表达式: {raw_request}")
        call_node = expr.body
        if not isinstance(call_node.func, ast.Name) or call_node.func.id != "tool_request":
            raise ValueError(f"不支持的调用形式: {raw_request}")

        args = [self._literal_or_source(node, raw_request) for node in call_node.args]
        kwargs = {
            (kw.arg or ""): self._literal_or_source(kw.value, raw_request)
            for kw in call_node.keywords
        }
        request_name = self._resolve_request_name(args, kwargs)
        return ParsedToolRequest(request_name=request_name, args=args, kwargs=kwargs, raw=raw_request)

    @staticmethod
    def _literal_or_source(node: ast.AST, raw_call: str) -> Any:
        try:
            return ast.literal_eval(node)
        except Exception:
            source = ast.get_source_segment(raw_call, node)
            return source if source is not None else ""

    @staticmethod
    def _resolve_tool_name(args: List[Any], kwargs: Dict[str, Any]) -> str:
        name = None
        if args and isinstance(args[0], str):
            name = args.pop(0)
        elif isinstance(kwargs.get("tool_name"), str):
            name = kwargs.pop("tool_name")
        elif isinstance(kwargs.get("name"), str):
            name = kwargs.pop("name")
        tool_name = str(name or "").strip()
        if not tool_name:
            raise ValueError("tool_call 缺少工具名。")
        return tool_name

    @staticmethod
    def _resolve_request_name(args: List[Any], kwargs: Dict[str, Any]) -> str:
        name = None
        if args and isinstance(args[0], str):
            name = args.pop(0)
        elif isinstance(kwargs.get("request"), str):
            name = kwargs.pop("request")
        elif isinstance(kwargs.get("name"), str):
            name = kwargs.pop("name")
        request_name = str(name or "").strip()
        if not request_name:
            raise ValueError("tool_request 缺少请求名。")
        return request_name

