"""会話生成アプリの例外."""


class TalkError(Exception):
    """Talk 機能の基底例外."""


class HolidayError(TalkError):
    """祝日API関連の基底例外."""


class HolidayNetworkError(HolidayError):
    """祝日APIへのネットワーク接続エラー."""


class HolidayTimeoutError(HolidayError):
    """祝日APIへのリクエストタイムアウト."""


class PlaceholderDataMissingError(TalkError):
    """プロンプト中のプレースホルダーに必要な設定データが不足している."""
