"""
config_templete.py

存放 create_config.py 使用的配置文件模板。
"""

from __future__ import annotations


def model_config_toml() -> str:
    """生成 model_config.toml 内容。"""
    return '''[llm.default]
model = "deepseek-chat"
base_url = "https://api.deepseek.com/v1"
api_key_env = "OPENAI_API_KEY"
temperature = 0.7
max_tokens = 8100
stream = true
'''
