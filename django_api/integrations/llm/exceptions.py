"""LLM関連の例外."""


class LLMConfigurationError(Exception):
    """LLM設定に関するエラー."""


class LLMClientError(Exception):
    """LLMクライアントの基底例外."""


class LLMTimeoutError(LLMClientError):
    """LLM APIタイムアウト."""
