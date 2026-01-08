"""AIアシスタント機能のカスタム例外."""


class AssistantError(Exception):
    """アシスタント機能の基底例外."""


class OpenAIAPIError(AssistantError):
    """OpenAI API呼び出しエラー."""


class OpenAITimeoutError(AssistantError):
    """OpenAI APIタイムアウト."""


class OpenAIConfigurationError(AssistantError):
    """OpenAI設定エラー（APIキー未設定など）."""


class ToolExecutionError(AssistantError):
    """ツール実行エラー."""
