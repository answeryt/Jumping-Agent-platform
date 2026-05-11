"""
config_templete.py

存放 create_config.py 使用的配置文件模板。
"""

from __future__ import annotations


def model_config_toml(model_name: str = "deepseek-chat") -> str:
    """生成 model_config.toml 内容。"""
    return f'''[llm.default]
model = "{model_name}"
base_url = ""
api_key_env = "OPENAI_API_KEY"
temperature = 0.7
max_tokens = 8100
stream = true
'''


def tool_config_toml() -> str:
    """生成 tool_config.toml 内容。"""
    return '''[tools.markdown_anchor]
source_template = "Context/standard_markdown.md"
finish_dir = "Finish_MarkDown"

[tools.call_agent.agent_aliases]
interaction = "interaction"
interaction_agent = "interaction"
planning = "planning"
planning_agent = "planning"
action = "action"
action_agent = "action"

[tools.tool_bridge]
required_fields = ["tool_name", "arguments", "call_id", "call_type", "result_binding"]

[tools.tool_bridge.field_aliases]
"tool name" = "tool_name"
"arguments" = "arguments"
"call id" = "call_id"
"type" = "call_type"
"result binding" = "result_binding"
"工具名称" = "tool_name"
"参数" = "arguments"
"调用id" = "call_id"
"调用 id" = "call_id"
"类型" = "call_type"
"结果绑定" = "result_binding"
'''
