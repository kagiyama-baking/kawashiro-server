"""LLMクライアントのカスタム例外."""

# llm_configから設定エラーを再エクスポート（利便性のため）
from llm_config.exceptions import OpenAIConfigurationError  # noqa: F401


class LLMClientError(Exception):
    """LLMクライアントの基底例外."""


class OpenAIAPIError(LLMClientError):
    """OpenAI API呼び出しエラー."""


class OpenAITimeoutError(LLMClientError):
    """OpenAI APIタイムアウト."""
