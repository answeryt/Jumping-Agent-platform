from __future__ import annotations

import ast
import builtins
import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .sandbox_tools import CodeSandbox, SandboxTool
except ImportError:  # pragma: no cover - legacy top-level imports
    from tools.sandbox_tools import CodeSandbox, SandboxTool


class _SandboxDiagnosticsEngine:
    """基于已加载项目执行运行、语法与导入诊断。"""

    def __init__(self, sandbox: CodeSandbox) -> None:
        # 诊断工具和读写工具共享同一个 CodeSandbox，因此运行前需要先 load_project。
        self._sb = sandbox

    def run_python(
        self,
        target: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        timeout_sec: int = 20,
    ) -> Dict[str, Any]:
        """运行 Python 文件或模块，并返回结构化结果。"""
        # run_python 会把项目根目录加入 PYTHONPATH，尽量模拟在项目根运行的效果。
        if self._sb.root is None:
            return self._error_result("[ERROR] 沙盒未加载，请先调用 load_project(path)")

        args = args or []
        command, run_target, working_dir = self._build_python_command(
            target=target,
            args=args,
            cwd=cwd,
        )
        env = os.environ.copy()
        project_root = str(self._sb.root)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            project_root
            if not existing_pythonpath
            else os.pathsep.join([project_root, existing_pythonpath])
        )

        try:
            completed = subprocess.run(
                command,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=env,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            return {
                "stdout": stdout,
                "stderr": (
                    stderr + ("\n" if stderr else "") + f"[TIMEOUT] 命令执行超过 {timeout_sec} 秒"
                ).strip(),
                "returncode": 124,
                "ok": False,
                "command": command,
                "target": run_target,
                "cwd": str(working_dir),
            }
        except Exception as exc:
            return self._error_result(f"[ERROR] 运行 Python 失败: {exc}")

        return {
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
            "ok": completed.returncode == 0,
            "command": command,
            "target": run_target,
            "cwd": str(working_dir),
        }

    def check_syntax(self, target: Optional[str] = None) -> Dict[str, Any]:
        """检查一个或多个 Python 文件的语法/缩进问题。"""
        # 语法检查只用 py_compile，不执行用户代码，适合在写入后快速验证。
        if self._sb.root is None or not self._sb._loaded:
            return self._error_result("[ERROR] 沙盒未加载，请先调用 load_project(path)")

        files = self._resolve_python_targets(target)
        if isinstance(files, str):
            return self._error_result(files)

        reports: List[Dict[str, Any]] = []
        success_count = 0
        for rel_path, abs_path in files:
            try:
                py_compile.compile(str(abs_path), doraise=True)
                reports.append(
                    {
                        "path": rel_path,
                        "ok": True,
                        "error_type": None,
                        "line": None,
                        "message": "OK",
                    }
                )
                success_count += 1
            except py_compile.PyCompileError as exc:
                err = exc.exc_value
                line = getattr(err, "lineno", None)
                reports.append(
                    {
                        "path": rel_path,
                        "ok": False,
                        "error_type": err.__class__.__name__,
                        "line": line,
                        "message": str(err),
                    }
                )
            except Exception as exc:
                reports.append(
                    {
                        "path": rel_path,
                        "ok": False,
                        "error_type": exc.__class__.__name__,
                        "line": None,
                        "message": str(exc),
                    }
                )

        failed = [r for r in reports if not r["ok"]]
        summary_lines = [
            f"检查文件数: {len(reports)}",
            f"通过: {success_count}",
            f"失败: {len(failed)}",
        ]
        if failed:
            summary_lines.append("--- 失败详情 ---")
            for item in failed:
                line_info = f":{item['line']}" if item["line"] else ""
                summary_lines.append(
                    f"- {item['path']}{line_info} [{item['error_type']}] {item['message']}"
                )

        return {
            "stdout": "\n".join(summary_lines),
            "stderr": "",
            "returncode": 0 if not failed else 1,
            "ok": not failed,
            "reports": reports,
        }

    def check_imports(self, target: Optional[str] = None) -> Dict[str, Any]:
        """静态分析项目内 import 语句，发现明显缺失或无法解析的导入。"""
        if self._sb.root is None or not self._sb._loaded:
            return self._error_result("[ERROR] 沙盒未加载，请先调用 load_project(path)")

        files = self._resolve_python_targets(target)
        if isinstance(files, str):
            return self._error_result(files)

        project_modules = self._build_project_module_index()
        diagnostics: List[Dict[str, Any]] = []
        for rel_path, _abs_path in files:
            content = self._sb.content_cache.get(rel_path, "")
            try:
                tree = ast.parse(content)
            except SyntaxError as exc:
                diagnostics.append(
                    {
                        "path": rel_path,
                        "line": exc.lineno,
                        "import": None,
                        "status": "syntax_error",
                        "message": f"语法错误阻止导入分析: {exc}",
                    }
                )
                continue

            package = self._module_name_from_rel(rel_path)
            package_parts = package.split(".") if package else []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        status, message = self._check_absolute_import(alias.name, project_modules)
                        if status != "ok":
                            diagnostics.append(
                                {
                                    "path": rel_path,
                                    "line": node.lineno,
                                    "import": alias.name,
                                    "status": status,
                                    "message": message,
                                }
                            )
                elif isinstance(node, ast.ImportFrom):
                    status, import_name, message = self._check_import_from(
                        module=node.module,
                        level=node.level,
                        aliases=[alias.name for alias in node.names],
                        package_parts=package_parts,
                        project_modules=project_modules,
                    )
                    if status != "ok":
                        diagnostics.append(
                            {
                                "path": rel_path,
                                "line": node.lineno,
                                "import": import_name,
                                "status": status,
                                "message": message,
                            }
                        )

            diagnostics.extend(self._check_annotation_names(rel_path, tree, project_modules))

        summary_lines = [
            f"检查文件数: {len(files)}",
            f"问题数: {len(diagnostics)}",
        ]
        if diagnostics:
            summary_lines.append("--- 导入诊断 ---")
            for item in diagnostics:
                line_info = f":{item['line']}" if item["line"] else ""
                import_name = item["import"] or "<syntax>"
                summary_lines.append(
                    f"- {item['path']}{line_info} [{item['status']}] {import_name} -> {item['message']}"
                )
        else:
            summary_lines.append("未发现明显的项目内导入解析问题。")

        return {
            "stdout": "\n".join(summary_lines),
            "stderr": "",
            "returncode": 0 if not diagnostics else 1,
            "ok": not diagnostics,
            "diagnostics": diagnostics,
        }

    def diagnose_python(self, target: Optional[str] = None) -> Dict[str, Any]:
        """组合执行语法检查与导入检查。"""
        syntax_result = self.check_syntax(target)
        import_result = self.check_imports(target)
        stdout_parts = [
            "=== Syntax Check ===",
            syntax_result.get("stdout", ""),
            "",
            "=== Import Check ===",
            import_result.get("stdout", ""),
        ]
        ok = bool(syntax_result.get("ok")) and bool(import_result.get("ok"))
        return {
            "stdout": "\n".join(stdout_parts).strip(),
            "stderr": "\n".join(
                part for part in [syntax_result.get("stderr", ""), import_result.get("stderr", "")] if part
            ),
            "returncode": 0 if ok else 1,
            "ok": ok,
            "syntax": syntax_result,
            "imports": import_result,
        }

    def _build_python_command(
        self,
        target: str,
        args: List[str],
        cwd: Optional[str],
    ) -> Tuple[List[str], str, Path]:
        python_executable = sys.executable or "python"
        working_dir = Path(cwd).resolve() if cwd else self._sb.root
        if target.startswith("-m "):
            module_name = target[3:].strip()
            command = [python_executable, "-m", module_name, *args]
            return command, module_name, working_dir

        abs_target, rel_target = self._resolve_file_target(target)
        if abs_target is None:
            raise FileNotFoundError(rel_target)
        command = [python_executable, str(abs_target), *args]
        return command, rel_target, abs_target.parent

    def _resolve_python_targets(self, target: Optional[str]) -> List[Tuple[str, Path]] | str:
        if target is None or target in ("", "*"):
            items = [
                (rel, self._sb.root / rel)
                for rel in sorted(self._sb.content_cache)
                if rel.endswith(".py")
            ]
            return items

        if target.endswith(".py") or "/" in target or "\\" in target:
            abs_target, rel_target = self._resolve_file_target(target)
            if abs_target is None:
                return f"[ERROR] 未找到 Python 文件: {target!r}"
            return [(rel_target, abs_target)]

        if target in self._sb.symbol_index:
            first = self._sb.symbol_index[target][0]
            return [(first.file, self._sb.root / first.file)]

        candidates = [
            (rel, self._sb.root / rel)
            for rel in sorted(self._sb.content_cache)
            if rel.endswith(".py") and target.lower() in rel.lower()
        ]
        if len(candidates) == 1:
            return candidates
        if len(candidates) > 1:
            paths = "\n".join(f"  {rel}" for rel, _ in candidates)
            return f"[ERROR] 目标匹配到多个 Python 文件，请使用更精确路径:\n{paths}"
        return f"[ERROR] 未找到 Python 文件: {target!r}"

    def _resolve_file_target(self, target: str) -> Tuple[Optional[Path], str]:
        normalized = target.replace("\\", "/")
        if self._sb.root is None:
            return None, normalized
        direct = self._sb.root / normalized
        if direct.exists():
            return direct.resolve(), direct.relative_to(self._sb.root).as_posix()
        candidates = [
            rel for rel in self._sb.content_cache
            if rel.endswith(".py") and normalized.lower() in rel.lower()
        ]
        if len(candidates) == 1:
            rel = candidates[0]
            return (self._sb.root / rel).resolve(), rel
        return None, normalized

    def _build_project_module_index(self) -> set[str]:
        modules: set[str] = set()
        if self._sb.root is None:
            return modules
        for rel in self._sb.content_cache:
            if not rel.endswith(".py"):
                continue
            module_name = self._module_name_from_rel(rel)
            if module_name:
                modules.add(module_name)
            parts = module_name.split(".") if module_name else []
            for idx in range(1, len(parts)):
                modules.add(".".join(parts[:idx]))
        return modules

    def _module_name_from_rel(self, rel_path: str) -> str:
        rel = rel_path.replace("\\", "/")
        if rel.endswith("/__init__.py"):
            rel = rel[: -len("/__init__.py")]
        elif rel.endswith(".py"):
            rel = rel[:-3]
        return rel.replace("/", ".").strip(".")

    def _check_absolute_import(self, name: str, project_modules: set[str]) -> Tuple[str, str]:
        root_name = name.split(".")[0]
        if name in project_modules or root_name in project_modules:
            return "ok", ""
        spec = self._find_module_spec(name)
        if spec is not None:
            return "ok", ""
        return "unresolved", "无法在项目内或当前 Python 环境中解析该导入"

    def _check_import_from(
        self,
        module: Optional[str],
        level: int,
        aliases: List[str],
        package_parts: List[str],
        project_modules: set[str],
    ) -> Tuple[str, str, str]:
        module = module or ""
        if level > 0:
            if level > len(package_parts):
                import_name = "." * level + module
                return "invalid_relative", import_name, "相对导入层级超出当前包深度"
            base_parts = package_parts[: len(package_parts) - level]
            if module:
                base_parts.extend(module.split("."))
            import_name = "." * level + module
            resolved = ".".join(part for part in base_parts if part)
            if resolved and resolved not in project_modules:
                return "unresolved_relative", import_name, f"项目内未解析到相对导入基模块: {resolved}"
            return "ok", import_name, ""

        import_name = module or ",".join(aliases)
        if module:
            status, message = self._check_absolute_import(module, project_modules)
            return status, import_name, message

        for alias in aliases:
            status, message = self._check_absolute_import(alias, project_modules)
            if status != "ok":
                return status, alias, message
        return "ok", import_name, ""

    def _check_annotation_names(
        self,
        rel_path: str,
        tree: ast.AST,
        project_modules: set[str],
    ) -> List[Dict[str, Any]]:
        diagnostics: List[Dict[str, Any]] = []
        imported_names = self._collect_imported_names(tree)
        available_names = set(imported_names)
        available_names.update(self._collect_local_definition_names(tree))
        available_names.update(dir(builtins))
        available_names.update({"None", "True", "False", "Ellipsis"})

        seen: set[Tuple[int, str]] = set()
        for annotation, line in self._iter_annotation_nodes(tree):
            for name in self._collect_annotation_name_uses(annotation):
                if name in available_names:
                    continue
                if self._annotation_name_resolves(name, project_modules):
                    continue
                key = (line, name)
                if key in seen:
                    continue
                seen.add(key)
                diagnostics.append(
                    {
                        "path": rel_path,
                        "line": line,
                        "import": name,
                        "status": "undefined_annotation_name",
                        "message": f"注解中使用了未导入或未定义的名称: {name}",
                    }
                )
        return diagnostics

    def _collect_imported_names(self, tree: ast.AST) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound_name = alias.asname or alias.name.split(".")[0]
                    if bound_name:
                        names.add(bound_name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    bound_name = alias.asname or alias.name
                    if bound_name:
                        names.add(bound_name)
        return names

    def _collect_local_definition_names(self, tree: ast.AST) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    names.update(self._collect_bound_names(target))
            elif isinstance(node, ast.AnnAssign):
                names.update(self._collect_bound_names(node.target))
            elif isinstance(node, ast.NamedExpr):
                names.update(self._collect_bound_names(node.target))
        return names

    def _collect_bound_names(self, node: ast.AST) -> set[str]:
        names: set[str] = set()
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                names.update(self._collect_bound_names(elt))
        return names

    def _iter_annotation_nodes(self, tree: ast.AST) -> List[Tuple[ast.AST, int]]:
        annotations: List[Tuple[ast.AST, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                    if arg.annotation is not None:
                        annotations.append((arg.annotation, getattr(arg.annotation, "lineno", arg.lineno)))
                if node.args.vararg and node.args.vararg.annotation is not None:
                    ann = node.args.vararg.annotation
                    annotations.append((ann, getattr(ann, "lineno", node.args.vararg.lineno)))
                if node.args.kwarg and node.args.kwarg.annotation is not None:
                    ann = node.args.kwarg.annotation
                    annotations.append((ann, getattr(ann, "lineno", node.args.kwarg.lineno)))
                if node.returns is not None:
                    annotations.append((node.returns, getattr(node.returns, "lineno", node.lineno)))
            elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
                annotations.append((node.annotation, getattr(node.annotation, "lineno", node.lineno)))
        return annotations

    def _collect_annotation_name_uses(self, annotation: ast.AST) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(annotation):
            if isinstance(node, ast.Name):
                names.add(node.id)
        return names

    def _annotation_name_resolves(self, name: str, project_modules: set[str]) -> bool:
        if name in project_modules:
            return True
        return self._find_module_spec(name) is not None

    def _find_module_spec(self, module_name: str) -> Any:
        script = (
            "import importlib.util, json, sys\n"
            "name = sys.argv[1]\n"
            "spec = importlib.util.find_spec(name)\n"
            "print(json.dumps({'found': spec is not None}))\n"
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py", encoding="utf-8") as handle:
            handle.write(script)
            script_path = Path(handle.name)
        try:
            completed = subprocess.run(
                [sys.executable, str(script_path), module_name],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            if completed.returncode != 0:
                return None
            payload = json.loads((completed.stdout or "").strip() or "{}")
            return payload if payload.get("found") else None
        except Exception:
            return None
        finally:
            try:
                script_path.unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def _error_result(message: str) -> Dict[str, Any]:
        return {"stdout": "", "stderr": message, "returncode": 1, "ok": False}


class SandboxDiagnosticsTool:
    """将运行与诊断能力暴露为 ToolBridge 可注册工具。"""

    def __init__(self, sandbox: CodeSandbox) -> None:
        self._engine = _SandboxDiagnosticsEngine(sandbox)

    def run_python(
        self,
        target: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        timeout_sec: int = 20,
    ) -> Dict[str, Any]:
        return self._engine.run_python(target=target, args=args, cwd=cwd, timeout_sec=timeout_sec)

    def check_syntax(self, target: Optional[str] = None) -> Dict[str, Any]:
        return self._engine.check_syntax(target)

    def check_imports(self, target: Optional[str] = None) -> Dict[str, Any]:
        return self._engine.check_imports(target)

    def diagnose_python(self, target: Optional[str] = None) -> Dict[str, Any]:
        return self._engine.diagnose_python(target)


_SANDBOX_DIAGNOSTIC_TOOL_NAMES = (
    "run_python",
    "check_syntax",
    "check_imports",
    "diagnose_python",
)


def build_sandbox_diagnostics_tool(sandbox_tool: SandboxTool) -> SandboxDiagnosticsTool:
    return SandboxDiagnosticsTool(sandbox_tool._sandbox)
