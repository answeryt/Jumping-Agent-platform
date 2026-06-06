from __future__ import annotations


def model_config_toml() -> str:
    """Return the default model_config.toml content for generated runtimes."""
    return '''[llm.default]
model = "deepseek-chat"
base_url = "https://api.deepseek.com/v1"
api_key_env = "OPENAI_API_KEY"
temperature = 0.7
max_tokens = 8100
stream = true
'''
