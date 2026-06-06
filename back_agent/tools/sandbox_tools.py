from __future__ import annotations
"""
sandbox_tools.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
代码沙盒工具：一次加载项目，Agent 通过简单工具调用精准定位代码。
核心思路
1. load_project(path) — 将本地项目一次性扫描、建立符号索引、解析配置，
后续所有查询均在内存中完成，无需额外子进程或 Python 脚本。
2. tree(depth)        — 展示项目目录树，.py 文件附带顶层符号名。
3. find(query)        — 按符号名 / 文件名 / 文本片段精准定位，三级 fallback。
4. get(target)        — 按类名/函数名/文件路径/"文件:行号"取出完整代码段。
5. config()           — 展示 .env / .toml / .json / .yaml 配置快照（key 自动脱敏）。
工具调用格式（极简）
tool_call("load_project", "C:/Users/.../my_project")
tool_call("tree")
tool_call("find", "BaseTool")
tool_call("get", "TextCleanTool")
tool_call("get", "tools/sandbox_tools.py:183")
tool_call("config")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────────────
@dataclass
class SymbolInfo:
    """一个 Python 类 / 函数 / 方法的位置信息。"""
    file: str       # 相对于项目根的路径（正斜杠）
    line: int       # 定义起始行（1-based）
    end_line: int   # 定义结束行（1-based）
    kind: str       # "class" | "function" | "method"
    parent: str     # 所属类名（method 专用，其余为空串）


# ──────────────────────────────────────────────────────────────────────
# CodeSandbox：项目索引与查询引擎
# ──────────────────────────────────────────────────────────────────────
class CodeSandbox:
    """
    项目代码沙盒：一次加载，多次查询。
    使用方式
    --------
    sandbox = CodeSandbox()
    summary = sandbox.load("C:/Users/.../project")
    print(sandbox.find("BaseTool"))
    print(sandbox.get("TextCleanTool"))
    """

    # 默认扫描的文件类型
    _DEFAULT_EXTS = {".py", ".md", ".toml", ".json", ".yaml", ".yml", ".env", ".txt"}
    # 需要解析为配置的文件名或后缀
    _CONFIG_NAMES = {".env", "model_config.toml", "settings.toml", "config.toml",
                     "config.json", "settings.json", "pyproject.toml"}
    _CONFIG_EXTS  = {".toml", ".json", ".yaml", ".yml"}
    # 脱敏关键字
    _SENSITIVE_KEYS = {"key", "secret", "password", "token", "passwd", "credential"}

    def __init__(self) -> None:
        # load_project 后这几个缓存会成为 back_agent 后续 find/get/config 的主要数据源。
        self.root: Optional[Path] = None
        self.symbol_index: Dict[str, List[SymbolInfo]] = {}
        self.content_cache: Dict[str, str] = {}   # rel_path → content
        self.config_store: Dict[str, Any] = {}    # rel_path → parsed dict / str
        self._loaded = False

    # ── 公开接口 ──────────────────────────────────────────────────────
    def load(
        self,
        path: str,
        include_exts: Optional[set] = None,
        max_file_kb: int = 512,
    ) -> str:
        """
        扫描并索引项目。
        参数
        ----
        path         : 项目根目录（绝对路径或相对路径）
        include_exts : 要扫描的文件后缀集合（默认见 _DEFAULT_EXTS）
        max_file_kb  : 单文件大小上限，超出则跳过（默认 512 KB）
        返回
        ----
        摘要字符串，包含文件数、符号数、配置项数。
        """
        # 每次 load_project 都重新建立索引，避免上一个项目的符号残留到当前任务。
        root = Path(path).resolve()
        if not root.exists():
            return f"[ERROR] 路径不存在: {root}"
        if not root.is_dir():
            return f"[ERROR] 不是目录: {root}"
        exts = include_exts or self._DEFAULT_EXTS
        max_bytes = max_file_kb * 1024
        # 重置状态
        self.root = root
        self.symbol_index.clear()
        self.content_cache.clear()
        self.config_store.clear()
        self._loaded = False
        skipped = 0
        for abs_path in sorted(root.rglob("*")):
            if not abs_path.is_file():
                continue
            # 跳过隐藏目录（.git 等）
            if any(p.name.startswith(".") and p.name not in (".env",)
                   for p in abs_path.relative_to(root).parents if p.name):
                continue
            is_dotenv = abs_path.name == ".env"
            if not is_dotenv and abs_path.suffix.lower() not in exts:
                continue
            if abs_path.stat().st_size > max_bytes:
                skipped += 1
                continue
            rel = abs_path.relative_to(root).as_posix()
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                skipped += 1
                continue
            self.content_cache[rel] = content
            # AST 符号提取
            if abs_path.suffix == ".py":
                # Python 文件额外走 AST，支持按类名/函数名精准 get/patch。
                self._index_symbols(rel, content)
            # 配置解析
            if self._is_config_file(abs_path):
                parsed = self._parse_config(abs_path.suffix.lower(),
                                            abs_path.name, content)
                if parsed is not None:
                    self.config_store[rel] = parsed
        self._loaded = True
        py_count     = sum(1 for f in self.content_cache if f.endswith(".py"))
        sym_count    = sum(len(v) for v in self.symbol_index.values())
        config_count = sum(
            len(v) if isinstance(v, dict) else 1
            for v in self.config_store.values()
        )
        lines = [
            f"项目已加载: {root}",
            f"  .py 文件      : {py_count} 个",
            f"  符号索引      : {sym_count} 条（类/函数/方法）",
            f"  配置项        : {config_count} 条",
            f"  总文件数      : {len(self.content_cache)} 个",
        ]
        if skipped:
            lines.append(f"  跳过（过大/读取失败）: {skipped} 个")
        return "\n".join(lines)

    def tree(self, depth: int = 3) -> str:
        """返回格式化目录树，.py 文件附带顶层符号名。"""
        if not self._loaded or self.root is None:
            return "[ERROR] 沙盒未加载，请先调用 load_project(path)"
        lines: List[str] = [f"{self.root.name}/"]
        self._render_tree(self.root, self.root, depth, 0, lines)
        return "\n".join(lines)

    def find(self, query: str) -> str:
        """
        三级精准定位：
          1. 符号名精确匹配（ClassName / function_name）
          2. 文件名模糊匹配
          3. 全文文本搜索（fallback）
        """
        if not self._loaded:
            return "[ERROR] 沙盒未加载，请先调用 load_project(path)"
        results: List[str] = []
        # 搜索顺序故意从强到弱：符号名 -> 文件名 -> 全文片段。
        # 级别 1：符号名精确匹配
        if query in self.symbol_index:
            for info in self.symbol_index[query]:
                ctx = f"  (in class {info.parent})" if info.parent else ""
                results.append(
                    f"[{info.kind}] {query}{ctx}\n"
                    f"    → {info.file}  行 {info.line}–{info.end_line}"
                )
        # 级别 2：文件名模糊匹配
        q_lower = query.lower()
        for rel_path in self.content_cache:
            stem = Path(rel_path).stem.lower()
            if q_lower in stem and rel_path not in [
                r.split("\n")[1].strip().lstrip("→ ")
                for r in results if "\n" in r
            ]:
                symbols = [
                    name for name, infos in self.symbol_index.items()
                    if any(i.file == rel_path and i.kind in ("class", "function")
                           for i in infos)
                ]
                sym_str = f"  symbols: {', '.join(symbols[:6])}" if symbols else ""
                results.append(f"[file] {rel_path}{sym_str}")
        # 级别 3：全文搜索（前 25 条）
        if not results:
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            for rel_path, content in self.content_cache.items():
                for i, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        results.append(f"{rel_path}:{i}:  {line.strip()}")
                        if len(results) >= 25:
                            break
                if len(results) >= 25:
                    break
        return "\n".join(results) if results else f"(未找到: {query!r})"

    def get(self, target: str, context_lines: int = 0) -> str:
        """
        按以下顺序解析 target：
          1. "file/path.py:42"  → 文件第 42 行附近（±context_lines，默认全文件）
          2. "ClassName"        → 按符号名取出完整类/函数定义
          3. "some/file.py"     → 返回文件完整内容（支持部分路径模糊匹配）
        """
        if not self._loaded:
            return "[ERROR] 沙盒未加载，请先调用 load_project(path)"
        # 模式 1：path:line
        # get 是后续写入工具的定位基础，支持符号、文件、文件:行号三种入口。
        colon_match = re.match(r"^(.+\.py):(\d+)$", target)
        if colon_match:
            file_part = colon_match.group(1)
            line_num  = int(colon_match.group(2))
            return self._get_around_line(file_part, line_num, context_lines or 20)
        # 模式 2：符号名
        if target in self.symbol_index:
            return self._get_symbol(target)
        # 模式 3：文件路径（精确或模糊）
        return self._get_file(target)

    def config(self) -> str:
        """展示所有已解析的配置文件内容（敏感 key 自动脱敏）。"""
        if not self._loaded:
            return "[ERROR] 沙盒未加载，请先调用 load_project(path)"
        if not self.config_store:
            return "(未找到配置文件)"
        sections: List[str] = []
        for rel_path, data in sorted(self.config_store.items()):
            sections.append(f"=== {rel_path} ===")
            if isinstance(data, dict):
                sections.append(self._format_dict(data, indent=0))
            else:
                sections.append(str(data))
        return "\n".join(sections)

    # ── AST 符号提取 ──────────────────────────────────────────────────
    def _index_symbols(self, rel_path: str, content: str) -> None:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                end = getattr(node, "end_lineno", node.lineno)
                self.symbol_index.setdefault(node.name, []).append(
                    SymbolInfo(file=rel_path, line=node.lineno,
                               end_line=end, kind="class", parent="")
                )
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_end = getattr(item, "end_lineno", item.lineno)
                        self.symbol_index.setdefault(item.name, []).append(
                            SymbolInfo(file=rel_path, line=item.lineno,
                                       end_line=m_end, kind="method",
                                       parent=node.name)
                        )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 只索引顶层函数（method 已经在 ClassDef 内处理）
                parent = getattr(node, "_parent_class", None)
                if parent is None:
                    end = getattr(node, "end_lineno", node.lineno)
                    self.symbol_index.setdefault(node.name, []).append(
                        SymbolInfo(file=rel_path, line=node.lineno,
                                   end_line=end, kind="function", parent="")
                    )

    # ── 目录树渲染 ────────────────────────────────────────────────────
    def _render_tree(
        self,
        root: Path,
        current: Path,
        max_depth: int,
        depth: int,
        lines: List[str],
    ) -> None:
        if depth >= max_depth:
            return
        prefix = "│   " * depth
        dirs: List[Path] = []
        files: List[Path] = []
        try:
            for child in sorted(current.iterdir()):
                if child.name.startswith(".") and child.name != ".env":
                    continue
                if child.name in ("__pycache__", "node_modules", ".git"):
                    continue
                (dirs if child.is_dir() else files).append(child)
        except PermissionError:
            return
        for d in dirs:
            lines.append(f"{prefix}├── {d.name}/")
            self._render_tree(root, d, max_depth, depth + 1, lines)
        for f in files:
            rel = f.relative_to(root).as_posix()
            annotation = ""
            if f.suffix == ".py" and rel in self.content_cache:
                syms = [
                    name for name, infos in self.symbol_index.items()
                    if any(i.file == rel and i.kind == "class" for i in infos)
                ]
                if syms:
                    annotation = f"  ({', '.join(syms[:4])})"
            lines.append(f"{prefix}├── {f.name}{annotation}")

    # ── get 辅助 ──────────────────────────────────────────────────────
    def _get_symbol(self, name: str) -> str:
        info = self.symbol_index[name][0]
        content = self.content_cache.get(info.file, "")
        all_lines = content.splitlines()
        snippet = "\n".join(all_lines[info.line - 1 : info.end_line])
        return f"# {info.file}  行 {info.line}–{info.end_line}  [{info.kind}]\n{snippet}"

    def _get_file(self, target: str) -> str:
        # 精确匹配
        if target in self.content_cache:
            return f"# {target}\n{self.content_cache[target]}"
        # 模糊匹配：末尾文件名 or 路径包含
        t_lower = target.lower().replace("\\", "/")
        candidates = [
            rel for rel in self.content_cache
            if t_lower in rel.lower() or Path(rel).name.lower() == t_lower
        ]
        if len(candidates) == 1:
            rel = candidates[0]
            return f"# {rel}\n{self.content_cache[rel]}"
        if len(candidates) > 1:
            listing = "\n".join(f"  {c}" for c in candidates)
            return f"(找到多个匹配，请用更精确的路径):\n{listing}"
        return f"(未找到: {target!r})"

    def _get_around_line(self, file_part: str, line_num: int, ctx: int) -> str:
        content = self.content_cache.get(file_part)
        if content is None:
            # 尝试模糊匹配
            for rel in self.content_cache:
                if file_part.lower() in rel.lower():
                    content = self.content_cache[rel]
                    file_part = rel
                    break
        if content is None:
            return f"(未找到文件: {file_part!r})"
        all_lines = content.splitlines()
        start = max(0, line_num - ctx - 1)
        end   = min(len(all_lines), line_num + ctx)
        snippet = "\n".join(
            f"{i + start + 1:4d} | {l}"
            for i, l in enumerate(all_lines[start:end])
        )
        return f"# {file_part}  行 {start + 1}–{end}\n{snippet}"

    # ── 配置文件解析 ──────────────────────────────────────────────────
    def _is_config_file(self, path: Path) -> bool:
        return (
            path.name in self._CONFIG_NAMES
            or path.suffix.lower() in self._CONFIG_EXTS
            or path.name == ".env"
        )

    def _parse_config(self, ext: str, name: str, content: str) -> Optional[Any]:
        try:
            if name == ".env" or ext == "":
                return self._parse_dotenv(content)
            if ext == ".toml":
                return self._parse_toml(content)
            if ext == ".json":
                return json.loads(content)
            if ext in (".yaml", ".yml"):
                return self._parse_yaml_simple(content)
        except Exception:
            pass
        return None

    def _parse_dotenv(self, content: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            result[key] = self._mask_sensitive(key, val)
        return result

    def _parse_toml(self, content: str) -> Dict[str, Any]:
        try:
            import tomllib  # Python 3.11+
            return tomllib.loads(content)
        except ImportError:
            pass
        try:
            import tomli  # type: ignore
            return tomli.loads(content)
        except ImportError:
            pass
        # 极简 fallback：只解析 key = "value" 顶层行
        result: Dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("[") and not line.startswith("#"):
                k, v = line.split("=", 1)
                key = k.strip()
                val = v.strip().strip('"').strip("'")
                result[key] = self._mask_sensitive(key, val)
        return result

    def _parse_yaml_simple(self, content: str) -> Dict[str, str]:
        """极简 YAML 解析：只处理 key: value 顶层行，无需外部依赖。"""
        result: Dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if ":" in line and not line.startswith("#") and not line.startswith("-"):
                k, _, v = line.partition(":")
                key = k.strip()
                val = v.strip().strip('"').strip("'")
                if key and val:
                    result[key] = self._mask_sensitive(key, val)
        return result

    def _mask_sensitive(self, key: str, val: str) -> str:
        k_lower = key.lower()
        if any(s in k_lower for s in self._SENSITIVE_KEYS):
            return (val[:4] + "****") if len(val) > 4 else "****"
        return val

    def _format_dict(self, data: Any, indent: int) -> str:
        lines: List[str] = []
        pad = "  " * indent
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    lines.append(f"{pad}{k}:")
                    lines.append(self._format_dict(v, indent + 1))
                else:
                    lines.append(f"{pad}{k} = {v!r}")
        else:
            lines.append(f"{pad}{data!r}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# SandboxTool：封装为工具调用接口
# ──────────────────────────────────────────────────────────────────────
class SandboxTool:
    """
    将 CodeSandbox 的方法暴露为 ToolBridge 可注册的工具。
    每个 ReactAgentWorkflow 实例持有一个 SandboxTool 实例，
    因此 load_project 加载的沙盒在整个对话生命周期内共享。
    """

    def __init__(self) -> None:
        self._sandbox = CodeSandbox()

    # ── 对外工具方法 ─────────────────────────────────────────────────
    def load_project(self, path: str, max_file_kb: int = 512) -> Dict[str, Any]:
        """
        将指定目录的代码加载到沙盒。必须在其他沙盒工具前调用一次。
        参数:
        - path       : 项目根目录（绝对路径，使用正斜杠）
        - max_file_kb: 单文件大小上限（KB），超出则跳过，默认 512
        """
        summary = self._sandbox.load(path, max_file_kb=max_file_kb)
        return {"stdout": summary, "stderr": "", "returncode": 0, "ok": True}

    def tree(self, depth: int = 3) -> Dict[str, Any]:
        """
        展示项目目录树，.py 文件自动附带顶层类名。
        参数:
        - depth: 展示深度（默认 3 层）
        """
        result = self._sandbox.tree(depth=depth)
        ok = not result.startswith("[ERROR]")
        return {"stdout": result, "stderr": "", "returncode": 0 if ok else 1, "ok": ok}

    def find(self, query: str) -> Dict[str, Any]:
        """
        精准定位：符号名 → 文件名 → 全文搜索（三级 fallback）。
        参数:
        - query: 类名、函数名、文件名（含或不含后缀）、任意文本片段
        示例:
          tool_call("find", "BaseTool")
          tool_call("find", "def run")
          tool_call("find", "sandbox_tools")
        """
        result = self._sandbox.find(query)
        ok = not result.startswith("[ERROR]")
        return {"stdout": result, "stderr": "", "returncode": 0 if ok else 1, "ok": ok}

    def get(self, target: str, context_lines: int = 0) -> Dict[str, Any]:
        """
        取出代码段，支持三种 target 格式：
          1. 类名/函数名     : tool_call("get", "TextCleanTool")
          2. 文件路径        : tool_call("get", "tools/sandbox_tools.py")
          3. 文件:行号       : tool_call("get", "tools/sandbox_tools.py:183")
        参数:
        - target       : 见上方说明
        - context_lines: 使用行号时上下展示的行数（默认 20）
        """
        result = self._sandbox.get(target, context_lines=context_lines)
        ok = not result.startswith("[ERROR]") and not result.startswith("(未找到")
        return {"stdout": result, "stderr": "", "returncode": 0 if ok else 1, "ok": ok}

    def config(self) -> Dict[str, Any]:
        """
        展示已加载项目的配置快照（.env / .toml / .json / .yaml）。
        敏感字段（含 key/secret/token/password）自动脱敏显示。
        示例:
          tool_call("config")
        """
        result = self._sandbox.config()
        ok = not result.startswith("[ERROR]")
        return {"stdout": result, "stderr": "", "returncode": 0 if ok else 1, "ok": ok}


# ──────────────────────────────────────────────────────────────────────
# 模块级工厂
# ──────────────────────────────────────────────────────────────────────
_SANDBOX_TOOL_NAMES = ("load_project", "tree", "find", "get", "config")


def build_sandbox_tool() -> SandboxTool:
    """创建一个新的 SandboxTool 实例（内含独立的 CodeSandbox）。"""
    return SandboxTool()
