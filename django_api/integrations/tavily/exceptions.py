"""Tavily API例外定義."""


class TavilyError(Exception):
    """Tavily関連エラーの基底クラス."""


class TavilyAPIError(TavilyError):
    """API呼び出しエラー."""


class TavilyConfigurationError(TavilyError):
    """API設定エラー（キー未設定等）."""
