"""
project_templete.py

定义 main_agent 项目的目录结构和占位文件模版。
create_project.py 从这里导入，不在脚本中内嵌结构定义。
"""

from __future__ import annotations


# 需要创建的目录列表（相对于项目根目录）
PROJECT_DIRS = [
    "Agent",
    "Model",
    "Workflow",
    "Context",
    "Prompt",
    "Skill",
    "Config",
    "Finish_MarkDown",
    "Test",
]

# 需要创建的占位文件（相对于项目根目录），值为文件初始内容
PROJECT_FILES = {
    ".env": "# 环境变量配置\nOPENAI_API_KEY=\nOPENAI_BASE_URL=\nMODEL_NAME=\n",
}