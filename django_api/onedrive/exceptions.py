"""OneDrive APIのカスタム例外クラス"""


class OneDriveException(Exception):
    """OneDrive API関連の基底例外クラス"""
    pass


class ConfigurationError(OneDriveException):
    """設定エラー（環境変数の不足、ファイルの不在など）"""
    pass


class AuthenticationError(OneDriveException):
    """認証エラー（トークン取得失敗、認証期限切れなど）"""
    pass


class UploadError(OneDriveException):
    """ファイルアップロードエラー"""
    pass


class FolderOperationError(OneDriveException):
    """フォルダ操作エラー（作成、削除など）"""
    pass


class ListOperationError(OneDriveException):
    """ファイル一覧取得エラー"""
    pass


class DeleteError(OneDriveException):
    """ファイル削除エラー"""
    pass


class NetworkError(OneDriveException):
    """ネットワーク接続エラー"""
    pass