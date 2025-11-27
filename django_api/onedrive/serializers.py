"""OneDriveアプリケーションのシリアライザー"""

from rest_framework import serializers


class FileUploadSerializer(serializers.Serializer):
    """ファイルアップロード用のシリアライザー"""

    file = serializers.FileField(required=True, help_text="アップロードするファイル")
    folder_path = serializers.CharField(
        required=False,
        default="/",
        help_text="OneDrive上のフォルダパス（デフォルト: ルート）",
    )
    file_name = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="保存時のファイル名（省略時は元のファイル名を使用）",
    )


class CreateFolderSerializer(serializers.Serializer):
    """フォルダ作成用のシリアライザー"""

    folder_name = serializers.CharField(required=True, help_text="作成するフォルダ名")
    parent_path = serializers.CharField(
        required=False, default="/", help_text="親フォルダのパス（デフォルト: ルート）"
    )


class ListFilesSerializer(serializers.Serializer):
    """ファイル一覧取得用のシリアライザー"""

    folder_path = serializers.CharField(
        required=False,
        default="/",
        help_text="取得するフォルダパス（デフォルト: ルート）",
    )


class DeleteFileSerializer(serializers.Serializer):
    """ファイル削除用のシリアライザー"""

    file_path = serializers.CharField(required=True, help_text="削除するファイルのパス")
    permanent_delete = serializers.BooleanField(
        required=False, default=False, help_text="完全削除（ごみ箱からも削除）"
    )


class DownloadFileSerializer(serializers.Serializer):
    """ファイルダウンロード用のシリアライザー"""

    file_path = serializers.CharField(
        required=True, help_text="ダウンロードするファイルのパス"
    )


class FileInfoSerializer(serializers.Serializer):
    """ファイル情報のシリアライザー"""

    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    size = serializers.IntegerField(read_only=True, required=False)
    created_at = serializers.DateTimeField(source="createdDateTime", read_only=True)
    modified_at = serializers.DateTimeField(
        source="lastModifiedDateTime", read_only=True
    )
    web_url = serializers.CharField(source="webUrl", read_only=True)
    download_url = serializers.CharField(
        source="@microsoft.graph.downloadUrl", read_only=True, required=False
    )
    is_folder = serializers.SerializerMethodField()

    def get_is_folder(self, obj):
        """フォルダかどうかを判定"""
        return "folder" in obj
