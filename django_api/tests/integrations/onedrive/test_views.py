"""OneDriveアプリのビューテスト"""

from unittest.mock import Mock, patch

import pytest
from rest_framework import status

from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.onedrive.exceptions import (
    DeleteError,
    FolderOperationError,
    ListOperationError,
    OneDriveFileNotFoundError,
    UploadError,
)

pytestmark = pytest.mark.django_db

CLIENT_PATCH = "integrations.onedrive.views.OneDriveMSGraphClient"

COMMON_HANDLED_ERRORS = [
    pytest.param(
        ConfigurationError("Missing configuration"),
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "サービスの設定に問題があります",
        id="ConfigurationError",
    ),
    pytest.param(
        AuthenticationError("Token expired"),
        status.HTTP_401_UNAUTHORIZED,
        "OneDriveへの認証に失敗しました",
        id="AuthenticationError",
    ),
    pytest.param(
        NetworkError("Connection timeout"),
        status.HTTP_502_BAD_GATEWAY,
        "OneDriveへの接続に失敗しました",
        id="NetworkError",
    ),
]


def _set_client_method_error(mock_client_class, method_name, exception):
    """クライアントメソッド呼び出し時に例外を発生させる"""
    if isinstance(exception, ConfigurationError):
        # ConfigurationError は初期化時に発生する想定
        mock_client_class.side_effect = exception
        return None
    mock_client = Mock()
    mock_client_class.return_value = mock_client
    getattr(mock_client, method_name).side_effect = exception
    return mock_client


@pytest.mark.api
class TestOneDriveUploadView:
    """OneDriveUploadViewのテストクラス"""

    @patch(CLIENT_PATCH)
    def test_upload_file_success(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """ファイルのアップロードが成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.return_value = {
            "name": "test_file.txt",
            "size": 17,
            "created_datetime": "2024-01-01T00:00:00Z",
            "web_url": "https://example.sharepoint.com/test_file.txt",
        }

        payload = {
            "file": mock_file,
            "folder_path": "/test_folder",
            "file_name": "custom_name.txt",
        }
        response = authenticated_client.post(
            "/onedrive/upload/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "ファイルが正常にアップロードされました"
        assert response.data["file_info"]["name"] == "test_file.txt"
        call_args = mock_client.upload_file_to_onedrive.call_args
        assert call_args.kwargs["file_name"] == "custom_name.txt"
        assert call_args.kwargs["folder_path"] == "/test_folder"

    def test_upload_file_without_authentication_fails(self, api_client, mock_file):
        """認証なしでファイルアップロードが失敗すること"""
        response = api_client.post(
            "/onedrive/upload/", {"file": mock_file}, format="multipart"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_upload_without_file_fails(self, authenticated_client):
        """ファイルなしでアップロードが失敗すること"""
        response = authenticated_client.post(
            "/onedrive/upload/", {"folder_path": "/test_folder"}, format="multipart"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file" in response.data

    @patch(CLIENT_PATCH)
    def test_upload_file_with_upload_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """UploadError 時に 400 を返すこと"""
        _set_client_method_error(
            mock_client_class, "upload_file_to_onedrive", UploadError("File too large")
        )
        response = authenticated_client.post(
            "/onedrive/upload/", {"file": mock_file}, format="multipart"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "File too large"

    @pytest.mark.parametrize(
        "exception, status_code, expected_msg", COMMON_HANDLED_ERRORS
    )
    @patch(CLIENT_PATCH)
    def test_upload_file_common_error_handling(
        self,
        mock_client_class,
        authenticated_client,
        mock_file,
        exception,
        status_code,
        expected_msg,
    ):
        """共通エラーハンドリング（Configuration / Authentication / Network）"""
        _set_client_method_error(
            mock_client_class, "upload_file_to_onedrive", exception
        )
        response = authenticated_client.post(
            "/onedrive/upload/", {"file": mock_file}, format="multipart"
        )
        assert response.status_code == status_code
        assert expected_msg in response.data["error"]

    @patch(CLIENT_PATCH)
    def test_upload_file_with_unexpected_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """予期しないエラー時に 500 を返すこと"""
        _set_client_method_error(
            mock_client_class, "upload_file_to_onedrive", Exception("Unexpected error")
        )
        response = authenticated_client.post(
            "/onedrive/upload/", {"file": mock_file}, format="multipart"
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "ファイルのアップロード中に問題が発生しました" in response.data["error"]


@pytest.mark.api
class TestOneDriveFolderView:
    """OneDriveFolderViewのテストクラス"""

    @patch(CLIENT_PATCH)
    def test_create_folder_success(self, mock_client_class, authenticated_client):
        """フォルダの作成が成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.create_folder.return_value = {
            "name": "New Folder",
            "folder": {},
            "created_datetime": "2024-01-01T00:00:00Z",
            "web_url": "https://example.sharepoint.com/New%20Folder",
        }

        payload = {"folder_name": "New Folder", "parent_path": "/documents"}
        response = authenticated_client.post("/onedrive/folder/", payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "フォルダが正常に作成されました"
        assert response.data["folder_info"]["name"] == "New Folder"
        mock_client.create_folder.assert_called_once_with(
            folder_name="New Folder", parent_path="/documents"
        )

    def test_create_folder_without_authentication_fails(self, api_client):
        """認証なしでフォルダ作成が失敗すること"""
        response = api_client.post("/onedrive/folder/", {"folder_name": "New Folder"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_folder_without_name_fails(self, authenticated_client):
        """フォルダ名なしでフォルダ作成が失敗すること"""
        response = authenticated_client.post(
            "/onedrive/folder/", {"parent_path": "/documents"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "folder_name" in response.data

    @patch(CLIENT_PATCH)
    def test_create_folder_with_folder_operation_error(
        self, mock_client_class, authenticated_client
    ):
        """FolderOperationError 時に 400 を返すこと"""
        _set_client_method_error(
            mock_client_class,
            "create_folder",
            FolderOperationError("Folder already exists"),
        )
        response = authenticated_client.post(
            "/onedrive/folder/", {"folder_name": "Existing Folder"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Folder already exists"

    @pytest.mark.parametrize(
        "exception, status_code, expected_msg", COMMON_HANDLED_ERRORS
    )
    @patch(CLIENT_PATCH)
    def test_create_folder_common_error_handling(
        self,
        mock_client_class,
        authenticated_client,
        exception,
        status_code,
        expected_msg,
    ):
        """共通エラーハンドリング（Configuration / Authentication / Network）"""
        _set_client_method_error(mock_client_class, "create_folder", exception)
        response = authenticated_client.post(
            "/onedrive/folder/", {"folder_name": "New Folder"}
        )
        assert response.status_code == status_code
        assert expected_msg in response.data["error"]

    @patch(CLIENT_PATCH)
    def test_create_folder_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に 500 を返すこと"""
        _set_client_method_error(
            mock_client_class, "create_folder", Exception("Unexpected error")
        )
        response = authenticated_client.post(
            "/onedrive/folder/", {"folder_name": "New Folder"}
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "フォルダの作成中に問題が発生しました" in response.data["error"]


@pytest.mark.api
class TestOneDriveListView:
    """OneDriveListViewのテストクラス"""

    @patch(CLIENT_PATCH)
    def test_list_files_success(self, mock_client_class, authenticated_client):
        """ファイル一覧の取得が成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.return_value = [
            {
                "name": "file1.pdf",
                "size": 1024000,
                "created_datetime": "2024-01-01T00:00:00Z",
                "web_url": "https://example.sharepoint.com/file1.pdf",
            },
            {
                "name": "folder1",
                "folder": {},
                "created_datetime": "2024-01-01T00:00:00Z",
                "web_url": "https://example.sharepoint.com/folder1",
            },
        ]

        response = authenticated_client.get(
            "/onedrive/list/", {"folder_path": "/documents"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["folder_path"] == "/documents"
        assert response.data["count"] == 2
        assert len(response.data["files"]) == 2
        assert response.data["files"][0]["name"] == "file1.pdf"
        mock_client.list_files.assert_called_once_with(folder_path="/documents")

    @patch(CLIENT_PATCH)
    def test_list_files_root_directory_default(
        self, mock_client_class, authenticated_client
    ):
        """folder_path 未指定時はルートディレクトリで呼ばれること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.return_value = []

        response = authenticated_client.get("/onedrive/list/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["folder_path"] == "/"
        assert response.data["count"] == 0
        mock_client.list_files.assert_called_once_with(folder_path="/")

    def test_list_files_without_authentication_fails(self, api_client):
        """認証なしでファイル一覧取得が失敗すること"""
        response = api_client.get("/onedrive/list/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch(CLIENT_PATCH)
    def test_list_files_with_list_operation_error(
        self, mock_client_class, authenticated_client
    ):
        """ListOperationError 時に 400 を返すこと"""
        _set_client_method_error(
            mock_client_class, "list_files", ListOperationError("Folder not found")
        )
        response = authenticated_client.get(
            "/onedrive/list/", {"folder_path": "/nonexistent"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Folder not found"

    @pytest.mark.parametrize(
        "exception, status_code, expected_msg", COMMON_HANDLED_ERRORS
    )
    @patch(CLIENT_PATCH)
    def test_list_files_common_error_handling(
        self,
        mock_client_class,
        authenticated_client,
        exception,
        status_code,
        expected_msg,
    ):
        """共通エラーハンドリング"""
        _set_client_method_error(mock_client_class, "list_files", exception)
        response = authenticated_client.get("/onedrive/list/")
        assert response.status_code == status_code
        assert expected_msg in response.data["error"]

    @patch(CLIENT_PATCH)
    def test_list_files_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に 500 を返すこと"""
        _set_client_method_error(
            mock_client_class, "list_files", Exception("Unexpected error")
        )
        response = authenticated_client.get("/onedrive/list/")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "ファイル一覧の取得中に問題が発生しました" in response.data["error"]


@pytest.mark.api
class TestOneDriveDeleteView:
    """OneDriveDeleteViewのテストクラス"""

    @patch(CLIENT_PATCH)
    def test_delete_file_success(self, mock_client_class, authenticated_client):
        """ファイルの削除が成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.return_value = None

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "ファイルが正常に削除されました"
        mock_client.delete_file.assert_called_once_with(
            file_path="/test_folder/test_file.txt", permanent_delete=False
        )

    def test_delete_file_without_authentication_fails(self, api_client):
        """認証なしでファイル削除が失敗すること"""
        response = api_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_without_file_path_fails(self, authenticated_client):
        """file_pathなしで削除が失敗すること"""
        response = authenticated_client.delete("/onedrive/delete/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file_path" in response.data

    @pytest.mark.parametrize(
        "permanent_delete_param, expected_kwarg",
        [
            ("?file_path=/x.txt&permanent_delete=true", True),
            ("?file_path=/x.txt&permanent_delete=false", False),
            ("?file_path=/x.txt", False),
        ],
        ids=["true", "false", "default"],
    )
    @patch(CLIENT_PATCH)
    def test_delete_file_permanent_delete_options(
        self,
        mock_client_class,
        authenticated_client,
        permanent_delete_param,
        expected_kwarg,
    ):
        """permanent_delete オプションが正しくクライアントに渡されること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.return_value = None

        response = authenticated_client.delete(
            f"/onedrive/delete/{permanent_delete_param}"
        )

        assert response.status_code == status.HTTP_200_OK
        mock_client.delete_file.assert_called_once_with(
            file_path="/x.txt", permanent_delete=expected_kwarg
        )

    @patch(CLIENT_PATCH)
    def test_delete_file_with_delete_error(
        self, mock_client_class, authenticated_client
    ):
        """DeleteError 時に 400 を返すこと"""
        _set_client_method_error(
            mock_client_class, "delete_file", DeleteError("File not found")
        )
        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "File not found"

    @pytest.mark.parametrize(
        "exception, status_code, expected_msg", COMMON_HANDLED_ERRORS
    )
    @patch(CLIENT_PATCH)
    def test_delete_file_common_error_handling(
        self,
        mock_client_class,
        authenticated_client,
        exception,
        status_code,
        expected_msg,
    ):
        """共通エラーハンドリング"""
        _set_client_method_error(mock_client_class, "delete_file", exception)
        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )
        assert response.status_code == status_code
        assert expected_msg in response.data["error"]

    @patch(CLIENT_PATCH)
    def test_delete_file_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に 500 を返すこと"""
        _set_client_method_error(
            mock_client_class, "delete_file", Exception("Unexpected error")
        )
        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "ファイルの削除中に問題が発生しました" in response.data["error"]


@pytest.mark.api
class TestOneDriveDownloadView:
    """OneDriveDownloadViewのテストクラス"""

    @patch(CLIENT_PATCH)
    def test_download_file_success(self, mock_client_class, authenticated_client):
        """ファイルのダウンロードが成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_file_content = b"test file content"
        mock_client.download_file.return_value = (mock_file_content, "test_file.txt")

        response = authenticated_client.get(
            "/onedrive/download/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/octet-stream"
        assert (
            response["Content-Disposition"]
            == "attachment; filename=\"test_file.txt\"; filename*=UTF-8''test_file.txt"
        )
        assert response.content == mock_file_content
        mock_client.download_file.assert_called_once_with(
            file_path="/test_folder/test_file.txt"
        )

    def test_download_file_without_authentication_fails(self, api_client):
        """認証なしでファイルダウンロードが失敗すること"""
        response = api_client.get(
            "/onedrive/download/?file_path=/test_folder/test_file.txt"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_download_without_file_path_fails(self, authenticated_client):
        """file_pathなしでダウンロードが失敗すること"""
        response = authenticated_client.get("/onedrive/download/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file_path" in response.data

    @patch(CLIENT_PATCH)
    def test_download_nonexistent_file_fails(
        self, mock_client_class, authenticated_client
    ):
        """OneDriveFileNotFoundError 時に 404 を返すこと"""
        _set_client_method_error(
            mock_client_class,
            "download_file",
            OneDriveFileNotFoundError("File not found"),
        )
        response = authenticated_client.get(
            "/onedrive/download/?file_path=/test_folder/nonexistent.txt"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"] == "File not found"

    @pytest.mark.parametrize(
        "exception, status_code, expected_msg",
        [
            pytest.param(
                AuthenticationError("Invalid credentials"),
                status.HTTP_401_UNAUTHORIZED,
                "OneDriveへの認証に失敗しました",
                id="AuthenticationError",
            ),
            pytest.param(
                NetworkError("Connection timeout"),
                status.HTTP_502_BAD_GATEWAY,
                "OneDriveへの接続に失敗しました",
                id="NetworkError",
            ),
        ],
    )
    @patch(CLIENT_PATCH)
    def test_download_common_error_handling(
        self,
        mock_client_class,
        authenticated_client,
        exception,
        status_code,
        expected_msg,
    ):
        """共通エラーハンドリング（Authentication / Network）"""
        _set_client_method_error(mock_client_class, "download_file", exception)
        response = authenticated_client.get(
            "/onedrive/download/?file_path=/test_folder/test_file.txt"
        )
        assert response.status_code == status_code
        assert expected_msg in response.data["error"]


@pytest.mark.api
class TestOneDriveCreateUploadSessionView:
    """OneDriveCreateUploadSessionViewのテストクラス"""

    @pytest.mark.parametrize(
        "folder_path, expected_path",
        [
            ("/backup", "/backup"),
            (None, "/"),
        ],
        ids=["with_folder", "default_root"],
    )
    @patch(CLIENT_PATCH)
    def test_create_upload_session_success(
        self,
        mock_client_class,
        authenticated_client,
        folder_path,
        expected_path,
    ):
        """アップロードセッションの作成が成功すること（folder_path 指定有無）"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._create_upload_session.return_value = (
            "https://graph.microsoft.com/upload/session/123"
        )

        payload = {"file_name": "large_file.tar.gz", "file_size": 100000000}
        if folder_path is not None:
            payload["folder_path"] = folder_path

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert (
            response.data["upload_url"]
            == "https://graph.microsoft.com/upload/session/123"
        )
        assert response.data["file_name"] == "large_file.tar.gz"
        assert response.data["file_size"] == 100000000
        assert response.data["folder_path"] == expected_path
        mock_client._create_upload_session.assert_called_once_with(
            file_name="large_file.tar.gz", folder_path=expected_path
        )

    def test_create_upload_session_without_authentication_fails(self, api_client):
        """認証なしでアップロードセッション作成が失敗すること"""
        payload = {"file_name": "large_file.tar.gz", "file_size": 100000000}
        response = api_client.post("/onedrive/upload-session/", payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize(
        "missing_field, payload",
        [
            ("file_name", {"file_size": 100000000}),
            ("file_size", {"file_name": "large_file.tar.gz"}),
        ],
    )
    def test_create_upload_session_missing_required_field_fails(
        self, authenticated_client, missing_field, payload
    ):
        """必須フィールド欠落時に 400 を返すこと"""
        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert missing_field in response.data

    @patch(CLIENT_PATCH)
    def test_create_upload_session_with_upload_error(
        self, mock_client_class, authenticated_client
    ):
        """UploadError 時に 400 を返すこと"""
        _set_client_method_error(
            mock_client_class,
            "_create_upload_session",
            UploadError("Failed to create session"),
        )
        payload = {"file_name": "large_file.tar.gz", "file_size": 100000000}
        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Failed to create session"

    @pytest.mark.parametrize(
        "exception, status_code, expected_msg", COMMON_HANDLED_ERRORS
    )
    @patch(CLIENT_PATCH)
    def test_create_upload_session_common_error_handling(
        self,
        mock_client_class,
        authenticated_client,
        exception,
        status_code,
        expected_msg,
    ):
        """共通エラーハンドリング"""
        _set_client_method_error(mock_client_class, "_create_upload_session", exception)
        payload = {"file_name": "large_file.tar.gz", "file_size": 100000000}
        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )
        assert response.status_code == status_code
        assert expected_msg in response.data["error"]

    @patch(CLIENT_PATCH)
    def test_create_upload_session_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に 500 を返すこと"""
        _set_client_method_error(
            mock_client_class,
            "_create_upload_session",
            Exception("Unexpected error"),
        )
        payload = {"file_name": "large_file.tar.gz", "file_size": 100000000}
        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert (
            "アップロードセッションの作成中に問題が発生しました"
            in response.data["error"]
        )


@pytest.mark.api
class TestOneDriveUploadChunkView:
    """OneDriveUploadChunkViewのテストクラス"""

    @patch(CLIENT_PATCH)
    def test_upload_chunk_in_progress(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """チャンクアップロードが継続中の場合、200を返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._upload_chunk.return_value = {"nextExpectedRanges": ["10485760-"]}

        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }
        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "in_progress"
        assert response.data["next_expected_ranges"] == ["10485760-"]

    @patch(CLIENT_PATCH)
    def test_upload_chunk_complete(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """チャンクアップロードが完了した場合、201を返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._upload_chunk.return_value = {
            "id": "file-id-123",
            "name": "large_file.tar.gz",
            "size": 100000000,
            "createdDateTime": "2024-01-01T00:00:00Z",
            "webUrl": "https://example.sharepoint.com/large_file.tar.gz",
        }

        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 90000000,
            "total_size": 100000000,
        }
        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "completed"
        assert "file_info" in response.data

    def test_upload_chunk_without_authentication_fails(self, api_client, mock_file):
        """認証なしでチャンクアップロードが失敗すること"""
        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }
        response = api_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize(
        "missing_field",
        ["upload_url", "chunk", "offset", "total_size"],
    )
    def test_upload_chunk_missing_required_field_fails(
        self, authenticated_client, mock_file, missing_field
    ):
        """必須フィールド欠落時に 400 を返すこと"""
        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }
        del payload[missing_field]

        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert missing_field in response.data

    @patch(CLIENT_PATCH)
    def test_upload_chunk_with_upload_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """UploadError 時に 400 を返すこと"""
        _set_client_method_error(
            mock_client_class, "_upload_chunk", UploadError("Chunk upload failed")
        )
        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }
        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Chunk upload failed"

    @pytest.mark.parametrize(
        "exception, status_code, expected_msg", COMMON_HANDLED_ERRORS
    )
    @patch(CLIENT_PATCH)
    def test_upload_chunk_common_error_handling(
        self,
        mock_client_class,
        authenticated_client,
        mock_file,
        exception,
        status_code,
        expected_msg,
    ):
        """共通エラーハンドリング"""
        _set_client_method_error(mock_client_class, "_upload_chunk", exception)
        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }
        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )
        assert response.status_code == status_code
        assert expected_msg in response.data["error"]

    @patch(CLIENT_PATCH)
    def test_upload_chunk_with_unexpected_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """予期しないエラー時に 500 を返すこと"""
        _set_client_method_error(
            mock_client_class, "_upload_chunk", Exception("Unexpected error")
        )
        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }
        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "チャンクのアップロード中に問題が発生しました" in response.data["error"]
