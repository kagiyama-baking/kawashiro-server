"""OneDrive APIのカスタム例外クラス"""


class OneDriveError(Exception):
    """OneDrive API関連の基底例外クラス"""


class ConfigurationError(OneDriveError):
    """設定エラー（環境変数の不足、ファイルの不在など）"""


class AuthenticationError(OneDriveError):
    """認証エラー（トークン取得失敗、認証期限切れなど）"""


class UploadError(OneDriveError):
    """ファイルアップロードエラー"""


class FolderOperationError(OneDriveError):
    """フォルダ操作エラー（作成、削除など）"""


class ListOperationError(OneDriveError):
    """ファイル一覧取得エラー"""


class DeleteError(OneDriveError):
    """ファイル削除エラー"""


class NetworkError(OneDriveError):
    """ネットワーク接続エラー"""


class FileNotFoundError(OneDriveError):
    """ファイルが見つからないエラー"""


class DownloadError(OneDriveError):
    """ファイルダウンロードエラー"""
