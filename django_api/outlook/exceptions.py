"""Outlook APIのカスタム例外クラス"""


class OutlookError(Exception):
    """Outlook API関連の基底例外クラス"""


class ConfigurationError(OutlookError):
    """設定エラー（環境変数の不足、ファイルの不在など）"""


class AuthenticationError(OutlookError):
    """認証エラー（トークン取得失敗、認証期限切れなど）"""


class CalendarError(OutlookError):
    """カレンダー操作エラー"""


class NetworkError(OutlookError):
    """ネットワーク接続エラー"""
