from __future__ import annotations
"""
sandbox_write_tools.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
代码沙盒写入工具：与 sandbox_tools.py 共享同一个 CodeSandbox 实例，
在磁盘写入和内存索引之间保持双向同步，提供三种写入粒度：

1. write_file(path, content)
   — 全量写入文件（新建或覆盖），自动创建父目录。
   — 若文件在已加载的项目范围内，立即更新符号索引，
     后续 find/get 可直接查询到变更内容。

2. patch_symbol(name, new_code)
   — 按类名 / 函数名精准替换，无需知道行号。
   — 工作流：get(name) 查看代码 → 修改 → patch_symbol(name, new_code)

3. replace_lines(file_path, start_line, end_line, new_code)
   — 按行号范围精准替换（适合修改配置块、import 区等无符号边界的代码）。
   — 工作流：get("file.py:行号") 确认范围 → replace_lines(...)

工具调用格式（极简）
tool_call("write_file",    "tools/my_tool.py",       "class MyTool:\n    pass\n")
tool_call("patch_symbol",  "calculate_score",        "def calculate_score(data):\n    ...")
tool_call("replace_lines", "config/settings.py", 43, 47, "MAX_RETRY = 5\nTIMEOUT = 30")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from pathlib import Path
from typing import Any, Dict, List

try:
    from .sandbox_tools import CodeSandbox, SandboxTool, build_sandbox_tool
except ImportError:  # pragma: no cover - legacy top-level imports
    from tools.sandbox_tools import CodeSandbox, SandboxTool, build_sandbox_tool


# ──────────────────────────────────────────────────────────────────────
# 内部写入引擎
# ──────────────────────────────────────────────────────────────────────
class _SandboxWriter:
    """
    持有 CodeSandbox 引用，执行磁盘写入并同步更新内存索引。
    所有写操作的公共逻辑均经由 _flush 完成：
      1. 写磁盘（write_text）
      2. 更新 content_cache
      3. 若为 .py 文件，清除旧符号并重建符号索引
    """

    def __init__(self, sandbox: CodeSandbox) -> None:
        self._sb = sandbox

    # ── 公共辅助 ──────────────────────────────────────────────────────
    def _flush(self, rel_path: str, new_content: str) -> None:
        """将修改后的内容写回磁盘，并同步更新沙盒内存索引。"""
        # 写入后立刻刷新 content_cache/symbol_index，保证下一次 find/get 看到最新代码。
        abs_path = self._sb.root / rel_path
        abs_path.write_text(new_content, encoding="utf-8")
        self._sb.content_cache[rel_path] = new_content

        if rel_path.endswith(".py"):
            # 清除该文件的全部旧符号
            for key in list(self._sb.symbol_index):
                self._sb.symbol_index[key] = [
                    s for s in self._sb.symbol_index[key]
                    if s.file != rel_path
                ]
                if not self._sb.symbol_index[key]:
                    del self._sb.symbol_index[key]
            # 重建该文件的符号索引
            self._sb._index_symbols(rel_path, new_content)

    @staticmethod
    def _normalize_code(code: str) -> List[str]:
        """确保代码字符串以换行符结尾，并拆成行列表（保留行尾换行符）。"""
        normalized = code if code.endswith("\n") else code + "\n"
        return normalized.splitlines(keepends=True)

    # ── 写入操作 ──────────────────────────────────────────────────────
    def write_file(self, path: str, content: str) -> str:
        """
        将 content 全量写入指定文件（新建或覆盖）。

        路径规则：
        - 绝对路径：直接使用
        - 相对路径：相对于已加载项目根目录；沙盒未加载时报错
        若目标文件在项目根目录范围内，同步更新沙盒索引；
        范围外的文件只写磁盘，不更新索引。
        """
        # write_file 是最粗粒度写入，适合新建文件或整体替换。
        target = Path(path)
        if not target.is_absolute():
            if self._sb.root is None:
                return (
                    "[ERROR] 沙盒未加载且传入了相对路径。"
                    "请先调用 load_project 或改用绝对路径。"
                )
            target = self._sb.root / path

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        # 判断是否在项目范围内
        rel: str | None = None
        if self._sb.root is not None:
            try:
                rel = target.relative_to(self._sb.root).as_posix()
            except ValueError:
                pass

        if rel is not None and self._sb._loaded:
            # 更新 content_cache 并重建符号索引
            self._sb.content_cache[rel] = content
            if rel.endswith(".py"):
                for key in list(self._sb.symbol_index):
                    self._sb.symbol_index[key] = [
                        s for s in self._sb.symbol_index[key] if s.file != rel
                    ]
                    if not self._sb.symbol_index[key]:
                        del self._sb.symbol_index[key]
                self._sb._index_symbols(rel, content)
            line_count = len(content.splitlines())
            return f"[OK] 已写入并更新索引: {rel}  ({line_count} 行)"

        line_count = len(content.splitlines())
        return f"[OK] 已写入（沙盒范围外，索引未更新）: {target}  ({line_count} 行)"

    def patch_symbol(self, name: str, new_code: str) -> str:
        """
        用 new_code 替换符号 name（类 / 函数 / 方法）在文件中的完整定义。

        new_code 须包含完整的 def/class 头和函数体，缩进与原代码一致。
        若同名符号在多个文件中均有定义，替换第一个（按 load_project 扫描顺序）。
        """
        if not self._sb._loaded:
            return "[ERROR] 沙盒未加载，请先调用 load_project(path)"

        if name not in self._sb.symbol_index:
            return (
                f"[ERROR] 未找到符号: {name!r}\n"
                "请先用 find() 确认符号名是否正确，或项目是否已加载。"
            )

        # patch_symbol 依赖 CodeSandbox 的 AST 索引，只替换一个完整 class/def/method 定义块。
        info = self._sb.symbol_index[name][0]
        original_content = self._sb.content_cache.get(info.file, "")
        all_lines = original_content.splitlines(keepends=True)

        patched_lines = self._normalize_code(new_code)

        # 替换 info.line ~ info.end_line（1-based，含）
        new_all_lines = (
            all_lines[: info.line - 1]
            + patched_lines
            + all_lines[info.end_line :]
        )
        new_content = "".join(new_all_lines)

        original_span = info.end_line - info.line + 1
        self._flush(info.file, new_content)
        return (
            f"[OK] 已替换 [{info.kind}] {name}\n"
            f"    文件 : {info.file}\n"
            f"    原行 : {info.line}–{info.end_line}（{original_span} 行）\n"
            f"    新行 : {len(patched_lines)} 行"
        )

    def replace_lines(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        new_code: str,
    ) -> str:
        """
        将 file_path 文件中第 start_line 到 end_line 行（含，1-based）替换为 new_code。

        支持路径精确匹配和末尾文件名模糊匹配，与 find/get 的路径风格一致。
        通常配合 get("file.py:行号") 确认行范围后使用。
        """
        if not self._sb._loaded:
            return "[ERROR] 沙盒未加载，请先调用 load_project(path)"

        # 精确匹配
        content = self._sb.content_cache.get(file_path)
        matched_path = file_path

        if content is None:
            # 末尾路径模糊匹配（与 sandbox_tools._get_file 风格一致）
            fp_lower = file_path.lower().replace("\\", "/")
            candidates = [
                rel for rel in self._sb.content_cache
                if fp_lower in rel.lower()
            ]
            if len(candidates) == 1:
                matched_path = candidates[0]
                content = self._sb.content_cache[matched_path]
            elif len(candidates) > 1:
                listing = "\n".join(f"  {c}" for c in candidates)
                return f"[ERROR] 找到多个匹配路径，请使用更精确的路径:\n{listing}"

        if content is None:
            return (
                f"[ERROR] 未找到文件: {file_path!r}\n"
                "请用 find() 或 tree() 确认路径后重试。"
            )

        all_lines = content.splitlines(keepends=True)
        total = len(all_lines)

        # replace_lines 不依赖 AST，适合改 import、配置块或其它没有符号边界的片段。
        if start_line < 1 or end_line > total or start_line > end_line:
            return (
                f"[ERROR] 行号超出范围: 文件共 {total} 行，"
                f"请求替换第 {start_line}–{end_line} 行。\n"
                "请用 get('file.py:行号') 重新确认行范围。"
            )

        patched_lines = self._normalize_code(new_code)

        new_all_lines = (
            all_lines[: start_line - 1]
            + patched_lines
            + all_lines[end_line :]
        )
        new_content = "".join(new_all_lines)

        original_span = end_line - start_line + 1
        self._flush(matched_path, new_content)
        return (
            f"[OK] 已替换 {matched_path} 第 {start_line}–{end_line} 行\n"
            f"    原行数: {original_span} 行 → 新行数: {len(patched_lines)} 行"
        )


# ──────────────────────────────────────────────────────────────────────
# SandboxWriteTool：封装为工具调用接口
# ──────────────────────────────────────────────────────────────────────
class SandboxWriteTool:
    """
    将 _SandboxWriter 的方法封装为 ToolBridge 可注册的工具接口。

    必须与对应的 SandboxTool 共享同一个 CodeSandbox 实例，
    才能保证读写操作对同一份内存索引生效。
    推荐通过 build_sandbox_write_tool(sandbox_tool) 工厂函数创建，
    而非直接实例化。
    """

    def __init__(self, sandbox: CodeSandbox) -> None:
        self._writer = _SandboxWriter(sandbox)

    # ── 对外工具方法 ─────────────────────────────────────────────────
    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        将 content 全量写入指定文件（新建或覆盖），自动创建父目录。
        若文件在已加载的项目范围内，自动更新沙盒索引，后续 find/get 立即生效。
        参数:
        - path   : 目标文件路径（绝对路径 或 相对于项目根的路径，正斜杠）
        - content: 完整文件内容
        示例:
          tool_call("write_file", "tools/my_tool.py", "class MyTool:\\n    pass\\n")
          tool_call("write_file", "C:/project/src/utils.py", "import os\\n...")
        """
        result = self._writer.write_file(path, content)
        ok = result.startswith("[OK]")
        return {"stdout": result, "stderr": "", "returncode": 0 if ok else 1, "ok": ok}

    def patch_symbol(self, name: str, new_code: str) -> Dict[str, Any]:
        """
        按符号名（类名 / 函数名）精准替换代码段，无需知道行号、无需重写整个文件。
        工作流：get(name) 查看现有代码 → 修改 → patch_symbol(name, new_code)
        参数:
        - name    : 类名或函数名（与 find/get 的符号名完全一致）
        - new_code: 完整新定义（含 def/class 头和完整函数体，保持正确缩进）
        示例:
          tool_call("patch_symbol", "calculate_score", \"\"\"def calculate_score(data):
              if not data:
                  return 0
              return sum(data) / len(data)
          \"\"\")
        """
        result = self._writer.patch_symbol(name, new_code)
        ok = result.startswith("[OK]")
        return {"stdout": result, "stderr": "", "returncode": 0 if ok else 1, "ok": ok}

    def replace_lines(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        new_code: str,
    ) -> Dict[str, Any]:
        """
        按行号范围精准替换文件内容，适合修改配置块、import 区等无符号边界的代码。
        工作流：get("file.py:行号") 查看行范围 → replace_lines(...) 替换
        参数:
        - file_path : 文件路径（相对于项目根，正斜杠；支持末尾路径模糊匹配）
        - start_line: 起始行号（1-based，含）
        - end_line  : 结束行号（1-based，含）
        - new_code  : 替换内容（字符串，末尾是否有换行均可）
        示例:
          tool_call("replace_lines", "config/settings.py", 43, 47, "MAX_RETRY = 5\\nTIMEOUT = 30")
        """
        result = self._writer.replace_lines(file_path, start_line, end_line, new_code)
        ok = result.startswith("[OK]")
        return {"stdout": result, "stderr": "", "returncode": 0 if ok else 1, "ok": ok}


# ──────────────────────────────────────────────────────────────────────
# 模块级常量与工厂
# ──────────────────────────────────────────────────────────────────────
_SANDBOX_WRITE_TOOL_NAMES = ("write_file", "patch_symbol", "replace_lines")


def build_sandbox_write_tool(sandbox_tool: SandboxTool) -> SandboxWriteTool:
    """
    从已有的 SandboxTool 实例提取其内部 CodeSandbox，
    创建与之共享内存索引的 SandboxWriteTool。

    用法示例（在 bridge 构建时）：
        read_tool = build_sandbox_tool()
        write_tool = build_sandbox_write_tool(read_tool)
        # 两者共享同一个 CodeSandbox，读写均操作同一份内存索引
    """
    return SandboxWriteTool(sandbox_tool._sandbox)
