"""HN Algolia API例外定義."""


class HNError(Exception):
    """HN関連エラーの基底クラス."""


class HNAPIError(HNError):
    """Algolia API呼び出しエラー."""


class HNNetworkError(HNAPIError):
    """ネットワーク接続エラー."""


class HNTimeoutError(HNAPIError):
    """リクエストタイムアウトエラー."""


class HNParseError(HNAPIError):
    """レスポンス解析エラー."""
