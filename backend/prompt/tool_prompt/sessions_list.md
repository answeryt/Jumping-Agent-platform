# sessions_list
当需要查看当前可见会话、筛选活跃会话或定位目标会话时，引导模型使用此工具。
调用格式：`tool_call("sessions_list", limit=10, includeLastMessage=True)`
请按需要设置 limit、label、agentId、search 或 includeLastMessage。
示例：列出最近活跃的会话。
示例：按 label 查找一个子会话。
示例：查看某个 agent 相关的会话摘要。
