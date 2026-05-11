---
name: agent-dev-skill
description: Agent 骨架补全 skill。引导你读懂 agent_builder 生成的 Agent 骨架文件，理解上下游分层架构，按正确模式补全 run 方法，用沙盒工具写回文件。
---

# Agent 骨架补全 Skill

## 必读：架构分层（动手前必须理解）

你工作的范围是由 `agent_builder` 创建的 workspace 项目目录。workspace 项目内部分为**上游框架层**和**下游业务层**，职责严格分离。

### 上游框架层（workspace 内的基类文件）—— 可读可改，但只能改接口定义，严禁写入业务逻辑

这些文件定义**接口契约与通用能力**，不包含任何具体业务逻辑。它们的职责是：

- **定义抽象接口**（`run` 等抽象方法）—— 规定下游子类必须实现哪些方法
- **提供通用工具方法**（`load_prompt()`、`chat_with_system()`）—— 供下游调用，无需重复实现
- **定义数据结构**（`FlowExecutionResult`、`AgentState`）—— 统一上下游的数据传递格式

> ⚠️ **严禁在上游文件中写入任何业务逻辑。** 不得在 `base_agent.py`、`base_model.py`、`base_flow.py` 等文件中添加具体的任务处理代码、条件判断或业务规则。业务逻辑只属于下游骨架文件（`xxx_agent.py`）。一旦误将业务逻辑写入上游，整个 workspace 的所有 Agent/Flow 都会受到污染。

```
workspace/your_project/
├── Agent/
│   └── base_agent.py       ← BaseAgent（抽象基类）+ PromptLoader —— 只定义接口，不含业务
├── Model/
│   └── base_model.py       ← BaseModel，提供 chat_with_system() 方法 —— 只封装模型调用
├── Workflow/
│   └── base_flow.py        ← BaseFlow + FlowExecutionResult / FlowTurnResult / ParsedFlowStep —— 只定义流程接口
└── Context/
    ├── markdown_schema.py  ← AgentState、AgentContext、AgentHandoff 等数据类 —— 只定义数据结构
    └── markdown_memroy.py  ← MarkdownMemory（上下文管理）—— 只提供通用上下文读写
```

### 下游业务层（workspace 内 agent_builder 生成的骨架文件）—— 你负责补全的内容

这些文件由 `agent_builder` 生成骨架，等待你填充业务逻辑：

```
workspace/your_project/
├── Agent/
│   └── xxx_agent.py    ← 继承 BaseAgent，你只需补全 run 方法（6行固定模式）
├── Prompt/
│   └── xxx_agent.md    ← system_prompt，run 方法从这里加载，不需要修改
├── Workflow/
│   └── xxx_flow.py     ← 继承 BaseFlow，由 flow 模板生成，编排逻辑已完整，通常不需要修改
├── Config/
│   └── model_config.toml
```

**Agent 的 run 方法里，不需要也不应该出现以下任何内容：**

- while 循环 / 步数控制
- messages 列表拼接
- 工具解析方法（`_extract_tool_name` 等）
- 工具执行方法（`_call_tool` 等）
- `self.model.generate()`（此方法不存在）
- `self.system_prompt`（此属性不存在）
- `self.tools`（此属性不存在）

---

## Phase 0：确认任务范围

在开始之前，先在 Thought 中回答：

- 骨架目录的绝对路径是什么？（这是唯一需要传给 `load_project` 的路径）
- 需要补全哪些文件？（通常是 `Agent/xxx_agent.py` 和 `Prompt/xxx_agent.md`）
- 是否存在 `Workflow/xxx_flow.py`？（若有，通常不需要修改它，只需补全它引用的各个 Agent）

---

## Phase 0.5：配置环境检查（动手写代码前必须完成）

> 此 Phase 在 `load_project` 之前执行，使用直接文件读取（非沙盒 `get`），路径全部为绝对路径。
> 根据 Phase 0 中记录的骨架绝对路径，可推算出 `back_agent` 的位置（通常为项目根目录下的 `back_agent/`）。

配置链路为：

```
back_agent/.env  →  back_agent/config/model_config.toml  →  config/settings.py  →  OpenAIModel
```

### 步骤 1：检查 `.env` 文件

直接读取 `back_agent/.env`（绝对路径），检查是否存在且包含有效 API Key。

- **文件不存在** → 创建文件，写入以下内容后**暂停，提示用户填写真实 Key 再继续**：
  ```
  OPENAI_API_KEY=<请填写你的 API Key>
  ```
- **文件存在但值是占位符**（含 `<`、`>` 或为空）→ 同样提示用户补全后再继续。
- **文件存在且值已填写** → 记录变量名（如 `OPENAI_API_KEY`），进入步骤 2。

### 步骤 2：检查 `model_config.toml`

直接读取 `back_agent/config/model_config.toml`（绝对路径），检查必填字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `model` | 不填| 模型名，如 `"deepseek-chat"`、`"gpt-4o"` |
| `api_key_env` | 必填 | 必须与 `.env` 中的变量名完全一致 |
| `base_url` | 条件必填 | 使用非 OpenAI 端点时（如 DeepSeek）必须填写 |
| `temperature` | 可选 | 默认 0.7 |
| `max_tokens` | 可选 | 默认无限制 |
| `stream` | 可选 | 默认 true |

- **文件不存在** → 创建标准模板：
  ```toml
  [llm.default]
  model = "deepseek-chat"
  base_url = "https://api.deepseek.com/v1"
  api_key_env = "OPENAI_API_KEY"
  temperature = 0.7
  max_tokens = 8100
  stream = true
  ```
- **字段缺失** → 补全缺失字段后继续。

### 步骤 3：一致性校验

在 Thought 中回答以下问题，全部通过后再进入 Phase 2：

- `model_config.toml` 里的 `api_key_env` 值是否与 `.env` 中的变量名**完全一致**？
- 若 `model` 是非 OpenAI 模型（如 `deepseek-*`），`base_url` 是否已填写？
- 若任一不一致 → 先修正，再继续。

---

## Phase 2：加载并读懂骨架

**执行以下工具调用：**

```
tool_call("load_project", "C:/绝对路径/workspace/your_project")
```

注意事项：

- `load_project` 只能调用一次。调用后沙盒根目录被设置为你传入的路径，后续所有 `get`、`write_file`、`patch_symbol` 的路径都必须是相对路径。
- 不要再 load_project 父目录（如 backend/）—— 这会让写文件操作指向错误位置。
- 不要用绝对路径调用 `get` / `write_file`（load_project 之后绝对路径会找不到文件）。

然后读取骨架文件：

```
tool_call("get", "Agent/xxx_agent.py")
tool_call("get", "Prompt/xxx_agent.md")
```

**读完后，在 Thought 中回答以下问题再继续：**

关于 `Agent/xxx_agent.py`：

- 文件里有哪些类？（应该有 `XxxAgentConfig` 和 `XxxAgent`）
- `__init__` 方法已经写好了吗？（骨架中已完整，不需要修改）
- 有没有 `run` 方法？（骨架中没有，这是唯一需要补全的）
- `super().__init__()` 传了哪四个参数？（只有 `agent_type`、`model`、`config`、`prompt_loader`，不能传其他参数）

关于 `Prompt/xxx_agent.md`：

- 这个文件的内容就是 system_prompt，`run` 方法会用 `self.load_prompt()` 加载它。
- "输出格式"一节规定了哪些字段？（模型会自动按这个格式输出，`run` 方法不需要构造格式）

---

## Phase 3：推断实现方案

**在 Thought 中完成以下推理，再进入 Phase 4 写代码。**

### Agent 的 run 方法（固定模式）

`run` 方法的唯一职责是：加载 system_prompt，驱动模型完成一次对话，返回模型的回复。

固定实现模式（6行）：

```python
def run(self, user_input: str, **kwargs) -> str:
    system_prompt = self.load_prompt()
    response = self.model.chat_with_system(
        system_message=system_prompt,
        user_message=user_input,
        temperature=self.config.temperature,
        max_tokens=self.config.max_tokens,
        stream=self.config.stream,
    )
    return str(response.get("content", "")).strip()
```

思考：这个 Agent 的业务逻辑有没有需要偏离这个模式的理由？
绝大多数情况答案是没有，直接用上面的模式即可。

不要为生成的 Agent 添加工具调用、工具解析、工具路由或 `self.tools` 相关代码。Agent 只通过模型和 Prompt 完成一次响应。

---

## Phase 4：写回完整代码

### 写 Agent 文件（推荐用 patch_symbol）

先确认 `XxxAgent` 类在骨架中已存在，然后用 `patch_symbol` 替换整个类：

```
tool_call("patch_symbol", "XxxAgent", '''class XxxAgent(BaseAgent):
    """
    负责"xxx"的 agent。
    注意：提示词不写在代码里，只从 Prompt 文件读取。
    """

    def __init__(
        self,
        model: Optional[BaseModel] = None,
        config: Optional[XxxAgentConfig] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        super().__init__(
            agent_type="xxx",
            model=model,
            config=config or XxxAgentConfig(),
            prompt_loader=prompt_loader,
        )

    def run(self, user_input: str, **kwargs) -> str:
        system_prompt = self.load_prompt()
        response = self.model.chat_with_system(
            system_message=system_prompt,
            user_message=user_input,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=self.config.stream,
        )
        return str(response.get("content", "")).strip()
''')
```

注意事项：

- `new_code` 必须包含整个类（从 `class XxxAgent:` 到最后一个方法结尾），如果 `new_code` 里没有 `__init__`，原来的 `__init__` 会消失。
- 收到 `[OK]` 即成功，不需要再用 `get` 确认。
- `patch_symbol` 的内容参数使用 `'''` 作为外层分隔符，代码内部的文档字符串使用 `"""` 即可，两者不会冲突。绝对不要在 `'''` 包裹的字符串内再用 `'''`。

### 当骨架缺少整个 Agent 类时，改用 write_file

如果骨架文件只有 Config 类而没有 Agent 类（需要新增整个类），用 `write_file` 覆盖全文件：

```
tool_call("write_file", "Agent/xxx_agent.py", '''from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from Agent.base_agent import BaseAgent, PromptLoader
from Model.base_model import BaseModel


@dataclass
class XxxAgentConfig:
    """XxxAgent 的运行参数。"""

    prompt_file: str = "xxx_agent.md"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None
    max_retries: int = 2


class XxxAgent(BaseAgent):
    """
    负责"xxx"的 agent。
    注意：提示词不写在代码里，只从 Prompt 文件读取。
    """

    def __init__(
        self,
        model: Optional[BaseModel] = None,
        config: Optional[XxxAgentConfig] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        super().__init__(
            agent_type="xxx",
            model=model,
            config=config or XxxAgentConfig(),
            prompt_loader=prompt_loader,
        )

    def run(self, user_input: str, **kwargs) -> str:
        system_prompt = self.load_prompt()
        response = self.model.chat_with_system(
            system_message=system_prompt,
            user_message=user_input,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=self.config.stream,
        )
        return str(response.get("content", "")).strip()
''')
```

对每个 Agent 文件重复以上过程，直到全部收到 `[OK]`。

---

## Phase 5：输出 Final Answer

所有文件收到 `[OK]` 后，输出 **Final Answer**，说明：

- 每个 Agent 的 `run` 方法补全了什么（通常一句话：加载 Prompt，调用模型，返回回复）
- 输出格式是否与 Prompt 文件中规定的结构一致

---

## 快速参考：BaseAgent 提供的属性和方法

| 名称 | 说明 |
|---|---|
| `self.model` | 模型实例，调用 `self.model.chat_with_system(system_message, user_message, ...)` |
| `self.config` | 配置 dataclass，含 `temperature`、`max_tokens`、`stream`、`prompt_file` |
| `self.load_prompt()` | 从 `config.prompt_file` 加载 system_prompt 字符串 |
| `self.agent_type` | str，agent 类型标识 |

BaseAgent 不提供（不要使用）：`self.system_prompt` · `self.tools` · `self.messages` · `self.model.generate()`

`super().__init__()` 只接受四个参数：`agent_type`、`model`、`config`、`prompt_loader`。不要传 `system_prompt`、`tools`、`max_retries`、`stream` 等，BaseAgent 没有这些参数。

---

## 快速参考：Workflow 骨架中的 6 种 Flow 类型

如果任务中涉及 `Workflow/` 目录，了解各类型含义（Flow 骨架通常不需要修改，只需补全它引用的各个 Agent）：

| Flow 类型 | 执行模式 | Agent 的输出约定 |
|---|---|---|
| `sequential_flow` | A → B → C 固定顺序 | 每个 agent 依次接收上一个的输出作为输入 |
| `router_flow` | dispatcher → 条件分支 | dispatcher 输出 `route_key: xxx` 决定走哪个 agent |
| `parallel_flow` | dispatcher → workers → aggregator | dispatcher 拆分任务，workers 并行，aggregator 汇总 |
| `loop_flow` | executor 与 evaluator 循环 | evaluator 输出 `verdict: pass` 或 `verdict: fail` |
| `debate_flow` | N 个参与者轮流 + moderator 判断 | moderator 输出 `consensus: true` 或 `consensus: false` |
| `hierarchical_flow` | manager → workers → manager 审查 | manager 输出 `assigned_to: xxx, subtask: xxx` |
