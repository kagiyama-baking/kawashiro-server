"""OneDrive APIのカスタム例外クラス"""


class OneDriveError(Exception):
    """OneDrive API関連の基底例外クラス"""


class UploadError(OneDriveError):
    """ファイルアップロードエラー"""


class FolderOperationError(OneDriveError):
    """フォルダ操作エラー（作成、削除など）"""


class ListOperationError(OneDriveError):
    """ファイル一覧取得エラー"""


class DeleteError(OneDriveError):
    """ファイル削除エラー"""


class OneDriveFileNotFoundError(OneDriveError):
    """ファイルが見つからないエラー"""


class DownloadError(OneDriveError):
    """ファイルダウンロードエラー"""
