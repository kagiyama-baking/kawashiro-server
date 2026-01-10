"""LLM設定関連の例外"""


class LLMConfigurationError(Exception):
    """LLM設定に関するエラー"""


class OpenAIConfigurationError(LLMConfigurationError):
    """OpenAI設定に関するエラー"""
