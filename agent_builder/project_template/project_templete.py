from __future__ import annotations


# 项目目录模板：create_project.py 会按这些列表在 sandbox 内创建 runtime 骨架。
PROJECT_ROOT_DIRS = [
    "runtime",
]

RUNTIME_PROJECT_DIRS = [
    "Agent",
    "Model",
    "Workflow",
    "Prompt",
    "Skill",
    "Config",
    "Test",
]

RUNTIME_PROJECT_FILES = {
    # .env 只提供占位，真实 key 由部署脚本或 backend/set_agent_api_key.py 写入。
    ".env": "# Runtime secrets\nOPENAI_API_KEY=\n",
}
