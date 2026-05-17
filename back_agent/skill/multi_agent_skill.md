---
name: multi-agent-skill
description: 用于补全存在显式协作链、上下游节点、handoff 或多节点运行时约束的多 agent 工作区。重点是让已有模板代码、runtime、flow 与 prompt 对齐，并交付真实可运行的多 agent 闭环。
---

# 核心理解

multi-agent workspace 更适合先看清全局，再成组推进实现。
与其把注意力分散在单个节点是否"像样"，更值得优先关注的是：整个 workspace 的运行闭环是否已经打通，runtime、flow 与 prompt 是否表达同一套 contract。

如果模板层已经提供默认 `run()`、统一 runtime runner、结构化 flow parser 或固定 schema，通常更适合顺着现有 contract 推理，而不是额外补出一层 orchestrator 专属骨架、局部上下文或伪协作机制。

## 推荐的整体节奏

在 multi-agent 任务里，通常可以先把工作分成三个较大的阶段来思考：

1. **全量分析**：先把项目结构、agent 职责、flow 入口、runtime 装配方式与 prompt 契约一起看清。
2. **批量修改**：在分析结论比较稳定之后，再把相关文件按组修改，而不是改一个文件就回头重新摸索一次。
3. **统一检验**：实现结束后，再集中检查运行入口、handoff 消费关系与最小可运行性。

这样的节奏往往比"读一点、改一点、再想一点"的推进方式更稳定，也更节省轮次。

## 第一阶段：更像做全局分析，而不是零碎试探

开始 multi-agent 任务时，通常值得先形成一份简短但完整的全局判断，再进入实现。
比较自然的分析重点包括：

- runtime 如何发现并装配 agent / workflow / tool 文件。
- flow 如何调度节点，节点执行时是否仍复用统一 runner。
- prompt 中出现的 `next_agent`、`next_task`、handoff、route 等字段，是否真的会被现有 runtime 或 flow 消费。
- 工作区已经提供了哪些 contract，哪些地方只是模板占位，哪些地方是真正的运行依赖。
- 当前缺口更像是"少了文件"，还是"契约没有对齐"。

如果已经能识别出共享 contract、同构骨架或一批需要联动的文件，往往可以先整理成"待修改清单"，例如：

- 需要补齐的 agent / prompt / flow / build 配置文件。
- 需要统一对齐的字段命名、handoff 表达、停止条件、入口约束。
- 需要一起检查的关键文件组，例如 runtime + flow + prompt。

当这份清单已经比较清楚时，再进入修改阶段，推理通常会顺得多。

## 第二阶段：更像成组修改，而不是逐文件往返

在 multi-agent workspace 中，很多问题并不是单文件问题，而是 contract 对齐问题。
因此实现时，通常更适合把相关文件按职责成组推进：

- 先集中处理运行闭环相关文件，如 runtime、flow、build plan、入口脚本。
- 再成组处理 agent 文件，保持角色、输入输出边界与 flow 约束一致。
- 再成组处理 prompt 文件，让 prompt 表达的协作关系与代码中的真实协作关系保持一致。

这样的推进方式通常能减少以下低效行为：

- 改完一个 agent 就重新探索项目。
- 看到一个字段就临时补一套 handoff 机制。
- 为了让单个文件"看起来完整"，引入 runtime 并不会消费的 route / next_agent / next_task 字段。
- 用很多小回合逐个创建文件，导致上下文越来越碎。

如果分析阶段已经确认了修改范围，实现阶段通常更适合优先完成一整批相关改动，再统一回看，而不是频繁在分析和实现之间来回切换。

## 第三阶段：更像统一验收，而不是边改边宣布完成

在主要实现结束后，再集中做一次一致性检查，通常更容易发现真正阻塞闭环的问题。
比较值得统一确认的是：

- runtime、flow 与 prompt 是否表达同一套协作关系与输出契约。
- flow 中每个节点是否仍走统一 runner，从而保持一致的执行入口。
- 是否仍残留明显 skeleton、半完成 flow、未消费的 handoff 字段或伪 route 字段。
- 如果工作区包含 `run_project.py` 这类运行入口，优先直接执行它作为主验证路径，而不是只做静态检查。
- 运行入口脚本时，要明确当前工作目录（cwd）是否位于 workspace 根目录；若脚本依赖相对路径，优先在 workspace 根目录下执行，避免把"路径碰巧正确"的一次运行误判为真正可运行。
- 验证时要尽量拿到真实运行报错、堆栈或失败节点，并继续沿着报错追到真正根因，而不是停在"文件已经补齐"这一层。
- 若入口脚本在某个环境下成功、在另一个环境下失败，要优先检查相对路径、cwd、环境变量、sys.path 或运行器包装差异，并以用户可复现的终端结果为准。
- 若入口脚本报错，问题是否已经继续追到闭环真正打通，而不是停在静态完整度上。

只有在关键链路真正跑通后，再把结果描述为 completed，通常会更稳妥。

## 协作表达上的引导

multi-agent prompt 更适合表达"当前节点的职责边界、输入、输出、与上下游关系"，而不是暗示每个节点都拥有自由调度整个系统的能力。

可以优先这样理解：

- 如果 runtime 并不消费 `next_agent`、`next_task` 一类字段，这些字段更适合作为辅助信息，而不是协作核心。
- 如果 flow 是固定顺序执行，prompt 更适合强调阶段职责，而不是赋予节点虚构的自由路由能力。
- 如果 handoff 由现有 flow / runtime 决定，prompt 更适合突出边界与输入输出，而不是让 agent 自己发明一套局部 orchestration。
- 如果当前框架不支持复杂协作，通常值得降级到受支持的最小可执行流程，而不是假装已经完整支持。

## 流水线数据传递质量

在顺序流水线（sequential flow）中，每个节点的 prompt 写法直接决定数据能否干净地传递给下游。以下几个问题值得在编写或审查 prompt 时逐一考虑。

**`result:` 字段给谁用？**

可以先问自己：这个节点的 `result:` 字段，是给下游节点直接处理的，还是给人读的自我推理摘要？如果 `result:` 里充斥着推理过程和自我分析，下游节点收到的实际上是冗余文字，而不是可处理的数据。`result:` 应该是当前节点的实际交付物。如果下游期望事件列表，`result:` 就应该是事件列表；如果下游期望分数与标签，`result:` 就应该是分数与标签。

**推理阶段与输出阶段是否分开？**

很多节点会要求执行推理阶段（如 agentic-reasoning）。这本身没有问题，但常见的陷阱是推理内容流入了 `result:` 字段，导致传递给下游的是推理日志而非结论。可以在 prompt 中明确区分：哪些内容是内部推理（可以出现在正文中），哪些是要传递给下游的结构化结果（只放入 `result:`）。

**终态节点是否优先回答用户？**

对于流水线中的最后一个节点，有一个容易被忽略的问题：它的首要任务是回答用户的原始问题，还是汇总整个流程？这两件事容易混淆。如果 prompt 只说"汇总全部上游输出"，节点会忠实地描述整个流程——但用户想要的是一个直接的答案。终态节点的 prompt 更适合明确写出："先直接回答用户问题，再引入上游分析作为支撑依据。"

**上游数据缺失时的降级策略是否已定义？**

顺序流水线中，某个节点如果未能产出有效的结构化数据，后续节点会收到一段冗余文字。如果 prompt 没有预期这种情况，节点容易陷入"等待数据"或"描述缺失"的循环。更合适的做法是在 prompt 中加入降级说明：当上游数据不是预期格式时，基于现有内容给出最合理的估计，而不是停下来等待或只报告缺失。

## 工具契约硬性禁令

以下行为在任何情况下都不允许，即便主观上认为"补充完善"或"让文件看起来更完整"：

- **禁止**在 workspace 的 `project_runtime.py` 中引入 `RuntimeToolExecutor`、`ToolBridge`、`BaseTool`、`ToolResult` 或任何本地工具桥接类。
- **禁止**在 workspace 中创建 `Tools/tool_bridge.py`、`Tools/tool_base.py` 或任何以本地 Python 函数注册方式提供工具的文件。
- **禁止**在 `RuntimeAgentRunner.run()` 中添加本地工具调用迭代循环（`parse_tool_calls` → `execute_calls` 类模式）。
- **禁止**在 `Prompt/*.md` 中写入具体 `sandbox_tool_call` 示例或猜测出的 MCP 工具名；sandbox 工具名只能来自运行时动态注入的 live catalog。
- workspace 工具的**唯一合法链路**是：agent 输出 `sandbox_tool_call` JSON → `_execute_sandbox_tool_calls()` 解析 → `BackendSandboxRuntime.call_tool()` 转发后端 MCP。此链路已由模板内置，不需要重新实现。
- `project_runtime.py` 的运行链路由模板固定，补全任务只应修改 `Agent/*.py` 和 `Prompt/*.md`，**不应改写** `project_runtime.py` 的工具执行路径。若 `project_runtime.py` 缺少 `_execute_sandbox_tool_calls` 等 MCP 函数，说明模板版本过旧，应从 `agent_builder/run_time_templete/creat_runtime.py` 重新生成，而不是自行添加 ToolBridge 替代方案。

## 常见的低效信号

如果出现以下情况，往往意味着推理节奏还可以再收束一些：

- prompt 列出了 handoff 字段，但 runtime / flow 并不会消费。
- flow 顺序由代码写死，却又让 prompt 假装具备自由路由能力。
- 以"完成""停止"等自然语言词作为主要停止条件，而不是依赖结构化字段或明确状态。
- 工作区已有模板 contract，但局部又复制出另一套近似基础设施。
- 分析、修改、检验被拆成很多零碎往返，导致轮次过多且上下文越来越散。
- `project_runtime.py` 中出现 `RuntimeToolExecutor` 或 `ToolBridge`，这是错误的工具链路，应立即回退到 MCP sandbox 契约。

## 完成判断

以下状态同时出现时，通常意味着 multi-agent workspace 已经更接近真正可运行：

- 协作责任归属已经清楚。
- prompt 主要表达职责边界，而不是虚构 orchestration 能力。
- runtime、flow 与 prompt 的 contract 基本一致。
- multi-agent flow 中的节点执行没有绕开统一 runner。
- 路由或 handoff 字段只在 runtime 真正需要时出现。
- 结果不仅让单个文件更完整，也让整个 workspace 更接近真实可运行状态。
- 若存在 `run_project.py` 或等价入口脚本，在宣布 completed 前应至少执行一次，并优先从 workspace 根目录验证其结果。
- 最终结论建立在真实运行验证之上，优先以 `python run_project.py` 或等价入口脚本的执行结果为依据；若不同执行环境结果不一致，应先解释差异根因，再决定是否可判定为完成，而不是建立在"模板看起来齐了"之上。
