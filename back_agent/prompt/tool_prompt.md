## 工具调用格式

在 **Action** 中调用工具时，必须使用以下函数调用风格，支持三种等价写法：

```
# 推荐：第一个位置参数为工具名
tool_call("tool_name", arg1, key=value)

# 关键字 tool_name
tool_call(tool_name="tool_name", key=value)

# 关键字 name
tool_call(name="tool_name", key=value)
```

**示例：**

```
Action: tool_call("find", "TODO")
Observation: src/utils.py:12:# TODO: refactor this
             src/main.py:45:# TODO: add error handling

Action: tool_call("run", cmd="git log --oneline -10", cwd="C:/repo")
Observation: a1b2c3d fix: handle edge case
             ...

Action: tool_call("python_batch", script="import re\nfrom pathlib import Path\nfor f in Path('src').rglob('*.py'):\n    t=f.read_text('utf-8'); f.write_text(t.replace('old_func','new_func'),'utf-8')", cwd="/repo")
Observation: [exit 0]
```

## 可用工具

所有工具均在本地 Shell 中执行，返回 `ShellResult`，包含字段：
`stdout`（标准输出）、`stderr`（标准错误）、`returncode`（退出码）、`ok`（是否成功）。

---

### run — 执行任意 Shell 命令

执行任意 Shell 命令字符串，是所有工具的底层接口。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `cmd` | str | 是 | Shell 命令（支持管道、重定向等） |
| `cwd` | str | 否 | 工作目录 |
| `timeout` | int | 否 | 超时秒数（默认 60） |
| `env` | dict | 否 | 额外环境变量 |

> **注意**：当前运行环境为 **Windows**，`run` 只适合执行 `git`、`python` 等跨平台命令。文件读写、搜索、批量修改请统一使用 `python_batch`；`ls`、`find`、`cat` 等 Linux 命令在此环境**不可用**。

```
Action: tool_call("run", cmd="git log --oneline -10", cwd="C:/repo")
```

---

### exec_script — 执行脚本文件

将脚本内容写入临时文件后用指定解释器执行，适合需要传完整脚本的场景。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `script` | str | 是 | 脚本源码 |
| `lang` | str | 否 | 解释器：`python` / `bash` / `node` / `ruby` / `perl`（默认 `python`） |
| `cwd` | str | 否 | 工作目录 |
| `timeout` | int | 否 | 超时秒数 |
| `script_args` | str | 否 | 传给脚本的额外命令行参数 |

```
Action: tool_call("exec_script", script="import sys\nprint(sys.version)", lang="python")
```

---

### python_batch — Python 脚本批量修改代码

执行一段 Python 脚本进行代码修改，是**文件内容替换的首选工具**（Windows/Linux 均可用）。适合：简单字符串替换、正则替换、多文件批量操作、AST 重构等一切需要编程逻辑的场景。

> **重要：Windows 环境下 `sed` 和 `perl_replace` 不可用，统一改用 `python_batch`（批量替换）或 `write_file`（整体写回）。**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `script` | str | 是 | Python 脚本内容（可使用 `pathlib` / `re` / `ast` / `glob` 等标准库） |
| `cwd` | str | 否 | 工作目录（脚本内相对路径以此为基准） |
| `timeout` | int | 否 | 超时秒数（默认 120） |

**用法一：简单字符串替换（替代 sed）**

```
Action: tool_call("python_batch", script="""
from pathlib import Path
for f in Path('src').rglob('*.py'):
    t = f.read_text(encoding='utf-8')
    nt = t.replace('import numpy', 'import numpy as np')
    if nt != t:
        f.write_text(nt, encoding='utf-8')
        print('Modified:', f)
""", cwd="C:/repo")
```

**用法二：正则替换（替代 perl_replace）**

```
Action: tool_call("python_batch", script="""
import re
from pathlib import Path
for f in Path('src').rglob('*.py'):
    t = f.read_text(encoding='utf-8')
    nt = re.sub(r'def (\\w+)_old\\(', r'def \\1(', t)
    if nt != t:
        f.write_text(nt, encoding='utf-8')
        print('Modified:', f)
""", cwd="C:/repo")
```

**用法三：读取单个文件、修改后写回**

```
Action: tool_call("python_batch", script="""
from pathlib import Path
p = Path('C:/repo/src/utils.py')
t = p.read_text(encoding='utf-8')
t = t.replace('OLD_CONSTANT', 'NEW_CONSTANT')
p.write_text(t, encoding='utf-8')
print('Done')
""")
```

**注意事项：**
- 脚本内**所有路径必须使用正斜杠**（`C:/Users/...`），禁止反斜杠（`C:\Users\...`）。
- 脚本字符串本身用三引号 `"""..."""` 包裹，内部不要再嵌套同类型三引号。
- 需要整体覆盖写入一个文件时，优先改用 `write_file`，更简洁。

---

### git_diff — 查看 git 变更

运行 `git diff` 查看工作区或暂存区的代码变更。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `cwd` | str | 否 | git 仓库路径 |
| `args` | str | 否 | 附加参数，如文件名、commit hash、`--stat`、`HEAD~3` 等 |
| `staged` | bool | 否 | `True` 则显示已暂存的变更（`--staged`），默认 `False` |

```
Action: tool_call("git_diff", cwd="/repo", args="src/utils.py")
Action: tool_call("git_diff", cwd="/repo", staged=True)
Action: tool_call("git_diff", cwd="/repo", args="HEAD~1 HEAD --stat")
```

---

## 代码沙盒工具（Code Sandbox）

沙盒工具将整个项目**一次性加载到内存索引**，后续所有查询均直接在索引中完成，无需写 Python 脚本、无需启动子进程。

> **使用规则**：探索项目前必须先调用一次 `load_project`，之后用 `find` / `get` / `tree` / `config` 精准定位，替代原来用 `python_batch` 读文件和搜索代码的做法。

---

### load_project — 加载项目到沙盒

扫描目录、建立符号索引、解析配置文件。**必须在其他沙盒工具前调用一次。**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | str | 是 | 项目根目录（绝对路径，使用正斜杠） |
| `max_file_kb` | int | 否 | 单文件大小上限（KB），默认 512 |

```
Action: tool_call("load_project", "C:/Users/86182/Desktop/agent")
Observation: 项目已加载: C:/Users/86182/Desktop/agent
  .py 文件      : 29 个
  符号索引      : 180 条（类/函数/方法）
  配置项        : 8 条
  总文件数      : 35 个
```

---

### tree — 查看项目目录树

展示项目结构，`.py` 文件自动附带顶层类名。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `depth` | int | 否 | 展示层级深度，默认 3 |

```
Action: tool_call("tree")
Action: tool_call("tree", depth=2)
```

---

### find — 精准定位符号 / 文件 / 文本

三级 fallback 查找：① 符号名精确匹配 → ② 文件名模糊匹配 → ③ 全文文本搜索。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `query` | str | 是 | 类名、函数名、文件名（含或不含后缀）、任意文本片段 |

```
Action: tool_call("find", "BaseTool")
Observation: [class] BaseTool
    → tools/tool_base.py  行 12–45

Action: tool_call("find", "def run")
Observation: agent/base_agent.py:41:  def run(self, user_input: str, **kwargs: Any) -> str:
             agent/react.py:22:  def run(self, user_input: str, **kwargs: Any) -> str:

Action: tool_call("find", "code_tools")
Observation: [file] tools/code_tools.py  symbols: ShellTool, ShellResult
```

---

### get — 取出代码段

按三种方式取出代码，**无需写任何 Python 脚本**：

| target 格式 | 说明 | 示例 |
|---|---|---|
| `ClassName` / `func_name` | 按符号名取出完整定义 | `"TextCleanTool"` |
| `path/to/file.py` | 取出整个文件内容（支持路径模糊匹配） | `"tools/code_tools.py"` |
| `path/to/file.py:行号` | 取出行号附近代码段（默认 ±20 行） | `"tools/code_tools.py:183"` |

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target` | str | 是 | 见上方格式说明 |
| `context_lines` | int | 否 | 行号模式时上下展示的行数，默认 20 |

```
Action: tool_call("get", "TextCleanTool")
Action: tool_call("get", "tools/code_tools.py")
Action: tool_call("get", "tools/code_tools.py:183")
Action: tool_call("get", "tools/code_tools.py:183", context_lines=30)
```

---

### config — 查看配置快照

展示 `.env` / `.toml` / `.json` / `.yaml` 的解析内容，含 `key`/`secret`/`token`/`password` 的字段自动脱敏（只显示前 4 位）。

```
Action: tool_call("config")
Observation:
=== .env ===
DEEPSEEK_API_KEY = 'sk-1a****'

=== config/model_config.toml ===
model = 'deepseek-chat'
base_url = 'https://api.deepseek.com/v1'
```

---

### write_file — 全量写入文件（沙盒感知）

将完整内容写入指定文件（新建或覆盖），自动创建父目录。
**若文件在已加载的项目范围内，沙盒索引自动同步，后续 find/get 立即可查。**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | str | 是 | 目标文件路径（绝对路径 或 相对于项目根，正斜杠） |
| `content` | str | 是 | 完整文件内容 |

```
Action: tool_call("write_file", "tools/my_tool.py", """
class MyTool:
    name = "my_tool"

    def run(self):
        pass
""")
Observation: [OK] 已写入并更新索引: tools/my_tool.py  (7 行)
```

---

### patch_symbol — 按符号名精准替换函数 / 类

**最推荐的代码修改工具。** 直接用符号名定位并替换完整的类或函数定义，
无需知道行号，无需重写整个文件。索引自动同步，改完立即可用 `get` 验证。

> **工作流**：`get(name)` 查看现有代码 → 修改 → `patch_symbol(name, new_code)`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | str | 是 | 类名或函数名（与 `find`/`get` 的符号名完全一致） |
| `new_code` | str | 是 | 完整新定义（含 `def`/`class` 头和完整函数体，保持正确缩进） |

```
Action: tool_call("get", "calculate_score")
Observation: # tools/scorer.py  行 12–17  [function]
def calculate_score(items):
    return len(items)

Action: tool_call("patch_symbol", "calculate_score", """def calculate_score(items):
    if not items:
        return 0.0
    return sum(items) / len(items)
""")
Observation: [OK] 已替换 [function] calculate_score
    文件 : tools/scorer.py
    原行 : 12–17（6 行）
    新行 : 5 行

Action: tool_call("get", "calculate_score")
Observation: # tools/scorer.py  行 12–16  [function]
def calculate_score(items):
    if not items:
        return 0.0
    return sum(items) / len(items)
```

---

### replace_lines — 按行号范围精准替换

适合修改**没有符号边界**的代码段，如 `import` 区、配置字典、注释块等。
索引自动同步。

> **工作流**：`get("file.py:行号")` 确认行范围 → `replace_lines(...)` 替换

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file_path` | str | 是 | 文件路径（相对于项目根，正斜杠；支持末尾路径模糊匹配） |
| `start_line` | int | 是 | 起始行号（1-based，含） |
| `end_line` | int | 是 | 结束行号（1-based，含） |
| `new_code` | str | 是 | 替换内容（末尾是否有换行均可） |

```
Action: tool_call("get", "config/settings.py:43", context_lines=3)
Observation:  40 | # 重试配置
  41 | MAX_RETRY = 3
  42 | TIMEOUT   = 10
  43 | DEBUG     = False

Action: tool_call("replace_lines", "config/settings.py", 41, 43, """MAX_RETRY = 5
TIMEOUT   = 30
DEBUG     = True
""")
Observation: [OK] 已替换 config/settings.py 第 41–43 行
    原行数: 3 行 → 新行数: 3 行
```

---

### 沙盒工具完整操作对比

| 操作 | 旧方式 | 新方式（沙盒工具）|
|---|---|---|
| 读一个文件 | `python_batch` 写 3 行脚本 | `tool_call("get", "file.py")` |
| 列目录结构 | `python_batch` 写 5 行脚本 | `tool_call("tree")` |
| 搜索符号/关键字 | `python_batch` 写 8 行脚本 | `tool_call("find", "SymbolName")` |
| 查看配置 | 多次 `python_batch` | `tool_call("config")` |
| **写入新文件** | `write_file`（不更新索引） | `tool_call("write_file", ...)` |
| **修改函数/类** | `python_batch` 正则替换 | `tool_call("patch_symbol", ...)` |
| **修改任意行段** | `python_batch` 写复杂脚本 | `tool_call("replace_lines", ...)` |
| **改完立即验证** | 需重新 `load_project` | 索引实时同步，直接 `get` |
| **首次使用** | —— | 需先调用 `load_project` |
