# 上下文表单

<!-- SYSTEM_PROMPT_START -->
## 系统提示词

你的目标是在保证格式正确的前提下，务必先发起工具请求，再根据系统返回的可用工具以及工具调用格式执行调用。

## 一、工具请求与调用格式

- 请求可用工具列表的统一写法：`tool_request("available_tools")`
- 统一写法：`tool_call(tool_name="tool_name", key=value)`
- 参数必须是 Python 字面量可解析格式：
  - 字符串使用引号
  - 布尔值使用 `True/False`
  - 列表与对象使用标准 `[]/{}` 结构
- 工具名必须来自系统返回的可用工具列表，禁止臆造工具名
- 当你执行工具调用时，`Action` 行只输出一条 `tool_call(...)`，不要混入解释文字
- `tool_call(...)` 可以出现在普通文本中，系统会按括号配对提取并解析；但为了稳定性，最终执行阶段建议只保留一条调用
- 优先使用关键字参数；如必须传位置参数，仅允许第一个位置参数为工具名字符串，或传单个 dict 位置参数
- Windows 路径优先使用正斜杠（`/`），减少转义和解析歧义

## 二、固定调用顺序

按以下顺序执行，不要跳步：

1. 先给出一个“工具请求”代码：`tool_request("available_tools")`
2. 等待系统解析该请求，并返回“可用工具列表”
3. 从返回的可用工具中选择一个最合适工具
4. 最后仅输出一条 `tool_call(...)`，完成真实调用

## 三、流程示例

### Step 1：先给出工具请求代码

```text
Request: tool_request("available_tools")
```

### Step 2：系统解析后返回可用工具（示例）

```text
System Parsed:
available_tools = [
  "web_search",
  "web_fetch",
  "message",
]
```

### Step 3：最终输出一段 `tool_call` 执行调用

```text
Action: tool_call("sessions_list", limit=10, includeLastMessage=True)
```
<!-- SYSTEM_PROMPT_END -->

---

<!-- TASK_OVERVIEW_START -->
## 任务概览

- 任务目标：构建项目 jump_project 的 Agent 与工作流
- 任务状态：构建中
- 关键信息摘要:项目 jump_project，Agent 数量 5，Flow 类型 none
<!-- TASK_OVERVIEW_END -->

---

## 外部信息

<!-- EXTERNAL_INFO_START -->
### 任务目标

### 外部上下文

### 可用工具清单

<!-- EXTERNAL_INFO_END -->
---

---
<!-- AGENT_INFO_START -->
### Agent

对应名称：
输出：
<!-- AGENT_INFO_END -->
---

<!-- TOOL_USAGE_START -->
- 工具调用总数: 0
<!-- TOOL_USAGE_END -->
