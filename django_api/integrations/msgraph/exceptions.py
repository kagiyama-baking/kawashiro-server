"""Microsoft Graph API共通の例外クラス"""


class MSGraphError(Exception):
    """Microsoft Graph API関連の基底例外クラス"""


class ConfigurationError(MSGraphError):
    """設定エラー（環境変数の不足、ファイルの不在など）"""


class AuthenticationError(MSGraphError):
    """認証エラー（トークン取得失敗、認証期限切れなど）"""


class NetworkError(MSGraphError):
    """ネットワーク接続エラー"""
