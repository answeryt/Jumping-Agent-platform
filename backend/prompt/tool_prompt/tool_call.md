# tool_call

当需要调用后端工具时，引导模型在 Action 中只输出一条 `tool_call(...)` 表达式。
推荐格式：`tool_call("tool_name", key=value)`；也可使用 `tool_call(tool_name="tool_name", key=value)` 或 `tool_call(name="tool_name", key=value)`。
工具名必须是已注册工具名称，参数使用 Python 字面量风格：字符串加引号，布尔值用 True/False，列表和对象保持可解析结构。
不要臆造未注册工具；不确定工具或参数时，先选择查询类工具获取上下文。
同一轮如果需要调用工具，不要在 Action 行混入解释文字、Markdown 或自然语言。
示例：`Action: tool_call("web_search", query="官方文档 最新版本")`
示例：`Action: tool_call("sessions_list", limit=10, includeLastMessage=True)`
示例：`Action: tool_call("update_plan", plan=[{"content": "分析需求", "status": "completed"}])`
