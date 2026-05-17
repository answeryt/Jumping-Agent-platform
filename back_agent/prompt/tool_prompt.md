## 工具调用格式

在 **Action** 中调用工具时，可以保持统一、稳定的函数调用风格。以下三种写法等价，通常选择一种并在同一轮里保持一致，会更利于推理连续性：

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
```

## 可用工具

当前工作流中**实际注册**的是一组与代码沙盒绑定的工具，返回统一结果结构：
`stdout`（标准输出）、`stderr`（标准错误）、`returncode`（退出码）、`ok`（是否成功）。

这些工具分为三类：

- **读工具**：`load_project`、`tree`、`find`、`get`、`config`
- **写工具**：`write_file`、`patch_symbol`、`replace_lines`
- **运行/诊断工具**：`run_python`、`check_syntax`、`check_imports`、`diagnose_python`

除以上工具外，不要调用未注册工具；如果需要某种操作，应优先在这组工具里选择最贴近的一种，而不是自行假设存在未注册的额外能力。

## 推荐的工作节奏

在需要补全一个已有 workspace 时，通常可以先把工具使用节奏收束成三个较大的阶段：

1. **先分析全局**：优先加载项目，并集中查看目录、配置、关键文件与共享 contract。
2. **再批量修改**：当待修改清单已经清楚后，再按文件组或职责组统一推进实现。
3. **最后统一验证**：将入口、flow、runtime、prompt、tooling 的一致性放到最后集中检查；如果涉及 Python 代码正确性，优先补做 `diagnose_python`，必要时再 `run_python` 验证真实运行。

这种方式往往比“看一个文件、改一个文件、再回头找下一个文件”的推进方式更省轮次，也更不容易把上下文打碎。

如果已经知道接下来会连续查询多个维度，通常可以在一次工具使用中成组完成，而不是拆成很多零散回合。

## 代码沙盒工具（Code Sandbox）

沙盒工具将整个项目**一次性加载到内存索引**，后续所有查询均直接在索引中完成，无需写 Python 脚本、无需启动子进程。

在项目探索阶段，通常可以先把注意力放在“建立全局判断”上：先 `load_project`，再围绕 `tree` / `find` / `get` / `config` 形成一份完整的项目分析，而不是边探索边零碎修改。

如果任务明显会涉及多个目录、多个 contract 或多类文件，往往值得先做一次相对完整的项目扫描，再开始批量改动。

> **使用规则**：探索项目前通常先调用一次 `load_project`，之后用 `find` / `get` / `tree` / `config` 精准定位。

---

### load_project — 加载项目到沙盒

扫描目录、建立符号索引、解析配置文件。它更像是后续分析阶段的起点：一旦项目被加载，后面的查询就可以围绕同一个索引连续展开，从而减少重复探索与无效回合。

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

作用：快速建立对项目结构的整体认识，确认有哪些目录、文件，以及 `.py` 文件里暴露了哪些顶层符号。它适合在项目初探阶段使用，也适合在已经定位到某个子目录后做结构补充确认。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `depth` | int | 否 | 展示层级深度，默认 3 |

```
Action: tool_call("tree")
Action: tool_call("tree", depth=2)
```

---

### find — 精准定位符号 / 文件 / 文本

作用：在已加载项目中做“定点查找”。它会依次尝试符号名、文件名和全文片段三层匹配，所以适合回答“某个类/函数/文件在哪”“某段文本出现在哪”这类问题。注意：`find` 返回的是**匹配结果**，不等于文件一定真实存在于某个固定路径，更不应该把代码引用误判成目录枚举结果。

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

Action: tool_call("find", "sandbox_tools")
Observation: [file] tools/sandbox_tools.py  symbols: CodeSandbox, SandboxTool
```

---

### get — 取出代码段

作用：把已经定位到的目标真正展开来看。它适合在 `find` 之后继续深入，也适合你已经知道明确文件路径、符号名或行号时直接读取内容。优先使用它来查看真实代码，而不是再额外猜测目录内容。

按三种方式取出代码，**无需写任何 Python 脚本**：

| target 格式 | 说明 | 示例 |
|---|---|---|
| `ClassName` / `func_name` | 按符号名取出完整定义 | `"TextCleanTool"` |
| `path/to/file.py` | 取出整个文件内容（支持路径模糊匹配） | `"tools/sandbox_tools.py"` |
| `path/to/file.py:行号` | 取出行号附近代码段（默认 ±20 行） | `"tools/sandbox_tools.py:183"` |

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target` | str | 是 | 见上方格式说明 |
| `context_lines` | int | 否 | 行号模式时上下展示的行数，默认 20 |

```
Action: tool_call("get", "TextCleanTool")
Action: tool_call("get", "tools/sandbox_tools.py")
Action: tool_call("get", "tools/sandbox_tools.py:183")
Action: tool_call("get", "tools/sandbox_tools.py:183", context_lines=30)
```

---

### config — 查看配置快照

作用：集中查看项目配置与环境变量快照，用来确认模型配置、工具配置、环境变量名以及运行时依赖是否准备齐全。适合在分析早期快速建立运行时判断，避免反复去单独翻配置文件。

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

作用：在需要新建文件或整文件重写时使用。它适合目标文件结构已经明确、没有必要做局部替换的场景。写入后索引会立即同步，因此后续可以直接继续 `find` / `get` 做验证，无需重新加载项目。

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

作用：做局部代码修改时的首选工具。它直接对类名或函数名对应的完整定义做替换，适合已经明确要修改哪个符号、但不想按整文件重写的场景。

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

作用：处理没有稳定符号边界的片段，比如 `import` 区、常量块、配置字典、提示词段落等。当你已经通过 `get("file.py:行号")` 确认了范围，它比整文件重写更稳，也比按符号替换更适合非函数/非类区域。

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

### check_syntax — 显式检查语法 / 缩进问题

作用：在 Python 代码改动后，用确定性的方式发现 `SyntaxError`、`IndentationError` 之类问题，而不是只依赖 `find/get` 间接观察。适合在新增文件、批量修改、修复缩进问题后收尾使用。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target` | str | 否 | 单个 `.py` 文件、符号名或路径片段；留空时检查当前已加载项目中的全部 `.py` 文件 |

```
Action: tool_call("check_syntax")
Action: tool_call("check_syntax", "workflow/react_agent_workflow.py")
```

---

### check_imports — 静态检查导入解析问题

作用：在不真正执行整个项目的情况下，尽早发现明显的导入错误，例如项目内相对导入层级错误、模块名拼错、依赖在当前环境中无法解析等。适合在新增模块、调整包结构、修改 import 区后使用。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target` | str | 否 | 单个 `.py` 文件、符号名或路径片段；留空时检查当前已加载项目中的全部 `.py` 文件 |

```
Action: tool_call("check_imports")
Action: tool_call("check_imports", "tools/sandbox_diagnostic_tools.py")
```

---

### diagnose_python — 汇总语法与导入诊断

作用：一条命令同时做 `check_syntax` 和 `check_imports`，适合在大部分 Python 修改结束后做集中收尾。默认应把它当作 Python 改动后的首选验证动作。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target` | str | 否 | 单个 `.py` 文件、符号名或路径片段；留空时检查全部已加载的 Python 文件 |

```
Action: tool_call("diagnose_python")
Action: tool_call("diagnose_python", "agent/base_agent.py")
```

---

### run_python — 运行 Python 文件或模块

作用：在完成静态诊断后，进一步验证脚本或模块在当前环境中是否真能运行。适合跑入口脚本、最小复现实验、局部模块验证，但不要把它误当成任意 shell 执行器。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target` | str | 是 | Python 文件路径，或 `-m module.name` 形式的模块目标 |
| `args` | list[str] | 否 | 传给目标脚本/模块的参数列表 |
| `cwd` | str | 否 | 工作目录；默认使用项目根，运行文件时会自动切到文件所在目录 |
| `timeout_sec` | int | 否 | 超时时间，默认 20 秒 |

```
Action: tool_call("run_python", "run_react_agent.py")
Action: tool_call("run_python", "-m pytest", args=["test/test_sandbox_tools.py", "-q"], timeout_sec=60)
```

---

### 沙盒工具完整操作对比

| 操作 | 旧方式 | 新方式（沙盒工具）|
|---|---|---|
| **写入新文件** | `write_file`（不更新索引） | `tool_call("write_file", ...)` |
| **改完立即验证** | 需重新扫描或手动重读 | 索引实时同步，直接 `get` |
| **首次使用** | —— | 先 `load_project` 更容易形成连续分析 |

## 更适合提速的使用方式

当任务规模较大、涉及多个目录或多类文件时，通常可以考虑下面的节奏：

- 先一次 `load_project` 建立索引。
- 再集中用 `tree`、`config`、`find`、`get` 形成全局分析摘要。
- 当修改范围已经清楚后，再成组使用写入或编辑类工具推进实现。
- 所有关键改动结束后，再统一做验证，而不是每改一个文件就重新回到项目探索。

如果某些查询彼此独立，也可以在一次工具调用中尽量成组完成，这通常有助于减少来回轮次。
