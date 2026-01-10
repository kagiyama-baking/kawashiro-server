"""LLMクライアントのカスタム例外."""


class LLMClientError(Exception):
    """LLMクライアントの基底例外."""


class OpenAIAPIError(LLMClientError):
    """OpenAI API呼び出しエラー."""


class OpenAITimeoutError(LLMClientError):
    """OpenAI APIタイムアウト."""
