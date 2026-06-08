# heartbeat_respond
当定时心跳要求汇报进展、是否通知用户或安排下次检查时，引导模型使用此工具。
请明确 outcome、notify 和 summary；notify=true 时补充简短 notificationText。
示例：汇报任务仍在进行且无需通知。
示例：发现阻塞并请求用户关注。
示例：任务完成后发送一句完成通知。
