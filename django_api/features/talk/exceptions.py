"""会話生成アプリの例外."""


class HolidayError(Exception):
    """祝日API関連の基底例外."""


class HolidayNetworkError(HolidayError):
    """祝日APIへのネットワーク接続エラー."""


class HolidayTimeoutError(HolidayError):
    """祝日APIへのリクエストタイムアウト."""
