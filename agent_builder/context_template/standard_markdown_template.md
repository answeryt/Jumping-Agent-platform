# 全局上下文标准（Markdown 协议）

---

<!-- AVAILABLE_TOOLS_START -->
## 可用工具列表（AVAILABLE_TOOLS）

本区域由系统在初始化时自动写入，列出当前运行时已注册的所有工具及其调用规范。
Agent 在决策阶段应参考此列表判断是否需要调用工具，并严格按照字段说明传参（注意！不得使用JSON）。

### call_agent
- 作用：调用指定的Agent（interaction / planning / action），你可以通过该工具调用其余的agent完成剩余的步骤任务。

<!-- AVAILABLE_TOOLS_END -->

---

<!-- STANDARD_FIELDS_START -->
### 通用字段（所有 Agent 可复用）
请按以下结构输出内部上下文；若当前任务中某字段暂无内容，请填写 `none`。

#### `AGENT_CONTEXT`
- 含义：描述当前 Agent 完成任务所需的背景信息与当前状态。
- 作用：让 Agent 知道“现在发生了什么、为什么做这件事”。
- 字段：`goal`、`user_request`、`known_info`、`phase`、`constraints`。

#### `AGENT_OUTPUT`
- 含义：记录当前 Agent 的最终产出内容。
- 作用：告诉下游“当前阶段已经产出了什么结果”。
- 字段：`result`。

#### `AGENT_TRACE`
- 含义：记录 Agent 如何完成任务的过程信息。
- 作用：用于调试、审计与可解释性追踪。
- 字段：`steps`、`skills_used`。

#### `AGENT_HANDOFF`
- 含义：向下一个 Agent 传递下一步执行指令。
- 作用：确保多 Agent 协作时任务连续、责任清晰。
- 字段：`next_agent`、`next_task`、`notes`。

### 输出规范（强约束）
- 字段 key 固定使用英文（如 `goal`、`next_task`），字段 value 可使用中文。
- 空值统一填写 `none`，禁止使用“无 / 暂无 / N/A”等其他写法。
- `AGENT_TRACE.steps` 必须使用 Markdown 列表格式（每行以 `- ` 开头）。
- 锚点命名必须与字段 key 对齐，格式为 `<!-- <AGENT_TYPE>_AGENT_<FIELD_NAME>_START -->` 与对应 `..._END`（示例：`next_task` -> `AGENT_NEXT_TASK`）。
<!-- STANDARD_FIELDS_END -->

<!-- AGENT_CONTEXT_START -->
#### AGENT_CONTEXT
goal: 

<!-- INTERACTION_AGENT_GOAL_START -->

<!-- INTERACTION_AGENT_GOAL_END -->

<!-- PLANNING_AGENTS_GOAL_START -->

<!-- PLANNING_AGENTS_GOAL_END -->

<!-- ACTION_AGENTS_GOAL_START -->

<!-- ACTION_AGENTS_GOAL_END -->
user_request: 

<!-- INTERACTION_AGENT_USER_REQUEST_START -->

<!-- INTERACTION_AGENT_USER_REQUEST_END -->

<!-- PLANNING_AGENTS_USER_REQUEST_START -->

<!-- PLANNING_AGENTS_USER_REQUEST_END -->

<!-- ACTION_AGENTS_USER_REQUEST_START -->

<!-- ACTION_AGENTS_USER_REQUEST_END -->
known_info: 
<!-- INTERACTION_AGENT_KNOWN_INFO_START -->

<!-- INTERACTION_AGENT_KNOWN_INFO_END -->

<!-- PLANNING_AGENTS_KNOWN_INFO_START -->

<!-- PLANNING_AGENTS_KNOWN_INFO_END -->

<!-- ACTION_AGENTS_KNOWN_INFO_START -->

<!-- ACTION_AGENTS_KNOWN_INFO_END -->
phase: 
<!-- INTERACTION_AGENT_PHASE_START -->

<!-- INTERACTION_AGENT_PHASE_END -->

<!-- PLANNING_AGENTS_PHASE_START -->

<!-- PLANNING_AGENTS_PHASE_END -->

<!-- ACTION_AGENTS_PHASE_START -->

<!-- ACTION_AGENTS_PHASE_END -->
constraints: 
<!-- INTERACTION_AGENT_CONSTRAINTS_START -->

<!-- INTERACTION_AGENT_CONSTRAINTS_END -->

<!-- PLANNING_AGENTS_CONSTRAINTS_START -->

<!-- PLANNING_AGENTS_CONSTRAINTS_END -->

<!-- ACTION_AGENTS_CONSTRAINTS_START -->

<!-- ACTION_AGENTS_CONSTRAINTS_END -->

<!-- AGENT_CONTEXT_END -->

--- 

<!-- AGENT_OUTPUT_START -->

#### AGENT_OUTPUT
result: 
<!-- INTERACTION_AGENT_RESULT_START -->

<!-- INTERACTION_AGENT_RESULT_END -->

<!-- PLANNING_AGENTS_RESULT_START -->

<!-- PLANNING_AGENTS_RESULT_END -->

<!-- ACTION_AGENTS_RESULT_START -->

<!-- ACTION_AGENTS_RESULT_END -->

#### AGENT_TRACE
steps:

<!-- INTERACTION_AGENT_STEPS_START -->

<!-- INTERACTION_AGENT_STEPS_END -->

<!-- PLANNING_AGENTS_STEPS_START -->

<!-- PLANNING_AGENTS_STEPS_END -->

<!-- ACTION_AGENTS_STEPS_START -->

<!-- ACTION_AGENTS_STEPS_END -->
skills_used:

<!-- INTERACTION_AGENT_SKILLS_USED_START -->

<!-- INTERACTION_AGENT_SKILLS_USED_END -->

<!-- PLANNING_AGENTS_SKILLS_USED_START -->

<!-- PLANNING_AGENTS_SKILLS_USED_END -->

<!-- ACTION_AGENTS_SKILLS_USED_START -->

<!-- ACTION_AGENTS_SKILLS_USED_END -->

#### AGENT_HANDOFF
next_agent:

<!-- INTERACTION_AGENT_NEXT_AGENT_START -->

<!-- INTERACTION_AGENT_NEXT_AGENT_END -->

<!-- PLANNING_AGENTS_NEXT_AGENT_START -->

<!-- PLANNING_AGENTS_NEXT_AGENT_END -->

<!-- ACTION_AGENTS_NEXT_AGENT_START -->

<!-- ACTION_AGENTS_NEXT_AGENT_END -->
next_task:

<!-- INTERACTION_AGENT_NEXT_TASK_START -->

<!-- INTERACTION_AGENT_NEXT_TASK_END -->

<!-- PLANNING_AGENTS_NEXT_TASK_START -->

<!-- PLANNING_AGENTS_NEXT_TASK_END -->

<!-- ACTION_AGENTS_NEXT_TASK_START -->

<!-- ACTION_AGENTS_NEXT_TASK_END -->
notes:
<!-- INTERACTION_AGENT_NOTES_START -->

<!-- INTERACTION_AGENT_NOTES_END -->

<!-- PLANNING_AGENTS_NOTES_START -->

<!-- PLANNING_AGENTS_NOTES_END -->

<!-- ACTION_AGENTS_NOTES_START -->

<!-- ACTION_AGENTS_NOTES_END -->

<!-- AGENT_OUTPUT_END -->

---

<!-- EXTERNAL_INFO_START -->
## 外部信息

### 来源范围

<!-- EXTERNAL_INFO_END -->
