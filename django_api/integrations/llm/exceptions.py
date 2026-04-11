"""LLM関連の例外."""


# 設定例外
class LLMConfigurationError(Exception):
    """LLM設定に関するエラー."""


class OpenAIConfigurationError(LLMConfigurationError):
    """OpenAI設定に関するエラー."""


# クライアント例外
class LLMClientError(Exception):
    """LLMクライアントの基底例外."""


class LLMTimeoutError(LLMClientError):
    """LLM APIタイムアウト."""


# 後方互換エイリアス
OpenAIAPIError = LLMClientError
OpenAITimeoutError = LLMTimeoutError
