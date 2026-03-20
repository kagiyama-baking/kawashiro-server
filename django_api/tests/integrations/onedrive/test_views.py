"""OneDriveアプリのビューテスト"""

from unittest.mock import Mock, patch

import pytest
from rest_framework import status


@pytest.mark.api
class TestOneDriveUploadView:
    """OneDriveUploadViewのテストクラス"""

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_file_success(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """ファイルのアップロードが成功すること"""
        # モッククライアントのセットアップ
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

        # クライアントメソッドが正しく呼ばれたことを確認
        mock_client.upload_file_to_onedrive.assert_called_once()
        call_args = mock_client.upload_file_to_onedrive.call_args
        assert call_args.kwargs["file_name"] == "custom_name.txt"
        assert call_args.kwargs["folder_path"] == "/test_folder"

    def test_upload_file_without_authentication_fails(self, api_client, mock_file):
        """認証なしでファイルアップロードが失敗すること"""
        payload = {"file": mock_file}

        response = api_client.post("/onedrive/upload/", payload, format="multipart")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_upload_without_file_fails(self, authenticated_client):
        """ファイルなしでアップロードが失敗すること"""
        payload = {"folder_path": "/test_folder"}

        response = authenticated_client.post(
            "/onedrive/upload/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file" in response.data

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_file_with_configuration_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """設定エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import ConfigurationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = ConfigurationError(
            "Missing configuration"
        )

        payload = {"file": mock_file}

        response = authenticated_client.post(
            "/onedrive/upload/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "サービスの設定に問題があります" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_file_with_authentication_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = AuthenticationError(
            "Token expired"
        )

        payload = {"file": mock_file}

        response = authenticated_client.post(
            "/onedrive/upload/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "OneDriveへの認証に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_file_with_upload_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """アップロードエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.onedrive.exceptions import UploadError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = UploadError("File too large")

        payload = {"file": mock_file}

        response = authenticated_client.post(
            "/onedrive/upload/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "File too large"

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_file_with_network_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = NetworkError(
            "Connection timeout"
        )

        payload = {"file": mock_file}

        response = authenticated_client.post(
            "/onedrive/upload/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "OneDriveへの接続に失敗しました" in response.data["error"]


@pytest.mark.api
class TestOneDriveFolderView:
    """OneDriveFolderViewのテストクラス"""

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
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

        # クライアントメソッドが正しく呼ばれたことを確認
        mock_client.create_folder.assert_called_once_with(
            folder_name="New Folder", parent_path="/documents"
        )

    def test_create_folder_without_authentication_fails(self, api_client):
        """認証なしでフォルダ作成が失敗すること"""
        payload = {"folder_name": "New Folder"}

        response = api_client.post("/onedrive/folder/", payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_folder_without_name_fails(self, authenticated_client):
        """フォルダ名なしでフォルダ作成が失敗すること"""
        payload = {"parent_path": "/documents"}

        response = authenticated_client.post("/onedrive/folder/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "folder_name" in response.data

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_folder_with_folder_operation_error(
        self, mock_client_class, authenticated_client
    ):
        """フォルダ操作エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.onedrive.exceptions import FolderOperationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.create_folder.side_effect = FolderOperationError(
            "Folder already exists"
        )

        payload = {"folder_name": "Existing Folder"}

        response = authenticated_client.post("/onedrive/folder/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Folder already exists"


@pytest.mark.api
class TestOneDriveListView:
    """OneDriveListViewのテストクラス"""

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
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

        # クライアントメソッドが正しく呼ばれたことを確認
        mock_client.list_files.assert_called_once_with(folder_path="/documents")

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_list_files_root_directory(self, mock_client_class, authenticated_client):
        """ルートディレクトリのファイル一覧が取得できること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.return_value = []

        response = authenticated_client.get("/onedrive/list/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["folder_path"] == "/"
        assert response.data["count"] == 0

        # デフォルトでルートディレクトリが指定されることを確認
        mock_client.list_files.assert_called_once_with(folder_path="/")

    def test_list_files_without_authentication_fails(self, api_client):
        """認証なしでファイル一覧取得が失敗すること"""
        response = api_client.get("/onedrive/list/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_list_files_with_list_operation_error(
        self, mock_client_class, authenticated_client
    ):
        """一覧取得操作エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.onedrive.exceptions import ListOperationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.side_effect = ListOperationError("Folder not found")

        response = authenticated_client.get(
            "/onedrive/list/", {"folder_path": "/nonexistent"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Folder not found"

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_file_with_unexpected_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """予期しないエラー時に適切なエラーレスポンスを返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = Exception("Unexpected error")

        payload = {"file": mock_file}

        response = authenticated_client.post(
            "/onedrive/upload/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "ファイルのアップロード中に問題が発生しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_folder_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に適切なエラーレスポンスを返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.create_folder.side_effect = Exception("Unexpected error")

        payload = {"folder_name": "New Folder"}

        response = authenticated_client.post("/onedrive/folder/", payload)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "フォルダの作成中に問題が発生しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_list_files_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に適切なエラーレスポンスを返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.side_effect = Exception("Unexpected error")

        response = authenticated_client.get("/onedrive/list/")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "ファイル一覧の取得中に問題が発生しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_folder_with_configuration_error(
        self, mock_client_class, authenticated_client
    ):
        """設定エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import ConfigurationError

        mock_client_class.side_effect = ConfigurationError("Missing configuration")

        payload = {"folder_name": "New Folder"}

        response = authenticated_client.post("/onedrive/folder/", payload)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "サービスの設定に問題があります" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_folder_with_authentication_error(
        self, mock_client_class, authenticated_client
    ):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.create_folder.side_effect = AuthenticationError("Token expired")

        payload = {"folder_name": "New Folder"}

        response = authenticated_client.post("/onedrive/folder/", payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "OneDriveへの認証に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_folder_with_network_error(
        self, mock_client_class, authenticated_client
    ):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.create_folder.side_effect = NetworkError("Connection timeout")

        payload = {"folder_name": "New Folder"}

        response = authenticated_client.post("/onedrive/folder/", payload)

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "OneDriveへの接続に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_list_files_with_configuration_error(
        self, mock_client_class, authenticated_client
    ):
        """設定エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import ConfigurationError

        mock_client_class.side_effect = ConfigurationError("Missing configuration")

        response = authenticated_client.get("/onedrive/list/")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "サービスの設定に問題があります" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_list_files_with_authentication_error(
        self, mock_client_class, authenticated_client
    ):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.side_effect = AuthenticationError("Token expired")

        response = authenticated_client.get("/onedrive/list/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "OneDriveへの認証に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_list_files_with_network_error(
        self, mock_client_class, authenticated_client
    ):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.side_effect = NetworkError("Connection timeout")

        response = authenticated_client.get("/onedrive/list/")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "OneDriveへの接続に失敗しました" in response.data["error"]


@pytest.mark.api
class TestOneDriveDeleteView:
    """OneDriveDeleteViewのテストクラス"""

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
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

        # クライアントメソッドが正しく呼ばれたことを確認
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

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_delete_file_with_configuration_error(
        self, mock_client_class, authenticated_client
    ):
        """設定エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import ConfigurationError

        mock_client_class.side_effect = ConfigurationError("Missing configuration")

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "サービスの設定に問題があります" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_delete_file_with_authentication_error(
        self, mock_client_class, authenticated_client
    ):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.side_effect = AuthenticationError("Token expired")

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "OneDriveへの認証に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_delete_file_with_delete_error(
        self, mock_client_class, authenticated_client
    ):
        """削除エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.onedrive.exceptions import DeleteError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.side_effect = DeleteError("File not found")

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "File not found"

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_delete_file_with_network_error(
        self, mock_client_class, authenticated_client
    ):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.side_effect = NetworkError("Connection timeout")

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "OneDriveへの接続に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_delete_file_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に適切なエラーレスポンスを返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.side_effect = Exception("Unexpected error")

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "ファイルの削除中に問題が発生しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_delete_file_with_permanent_delete_true(
        self, mock_client_class, authenticated_client
    ):
        """完全削除オプションがTrueの場合、ごみ箱からも削除されること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.return_value = None

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt&permanent_delete=true"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "ファイルが正常に削除されました"

        # クライアントメソッドがpermanent_delete=Trueで呼ばれたことを確認
        mock_client.delete_file.assert_called_once_with(
            file_path="/test_folder/test_file.txt", permanent_delete=True
        )

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_delete_file_with_permanent_delete_false(
        self, mock_client_class, authenticated_client
    ):
        """完全削除オプションがFalseの場合、通常削除されること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.return_value = None

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt&permanent_delete=false"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "ファイルが正常に削除されました"

        # クライアントメソッドがpermanent_delete=Falseで呼ばれたことを確認
        mock_client.delete_file.assert_called_once_with(
            file_path="/test_folder/test_file.txt", permanent_delete=False
        )

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_delete_file_without_permanent_delete_parameter(
        self, mock_client_class, authenticated_client
    ):
        """完全削除オプションが指定されない場合、デフォルトでFalse（通常削除）になること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.delete_file.return_value = None

        response = authenticated_client.delete(
            "/onedrive/delete/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_200_OK

        # クライアントメソッドがpermanent_delete=Falseで呼ばれたことを確認
        mock_client.delete_file.assert_called_once_with(
            file_path="/test_folder/test_file.txt", permanent_delete=False
        )


@pytest.mark.api
class TestOneDriveDownloadView:
    """OneDriveDownloadViewのテストクラス"""

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_download_file_success(self, mock_client_class, authenticated_client):
        """ファイルのダウンロードが成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # ファイル内容とファイル名をモック
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

        # クライアントメソッドが正しく呼ばれたことを確認
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

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_download_nonexistent_file_fails(
        self, mock_client_class, authenticated_client
    ):
        """存在しないファイルのダウンロードが失敗すること"""
        from integrations.onedrive.exceptions import OneDriveFileNotFoundError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.download_file.side_effect = OneDriveFileNotFoundError(
            "File not found"
        )

        response = authenticated_client.get(
            "/onedrive/download/?file_path=/test_folder/nonexistent.txt"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"] == "File not found"

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_download_with_authentication_error(
        self, mock_client_class, authenticated_client
    ):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.download_file.side_effect = AuthenticationError(
            "Invalid credentials"
        )

        response = authenticated_client.get(
            "/onedrive/download/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "OneDriveへの認証に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_download_with_network_error(self, mock_client_class, authenticated_client):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.download_file.side_effect = NetworkError("Connection timeout")

        response = authenticated_client.get(
            "/onedrive/download/?file_path=/test_folder/test_file.txt"
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "OneDriveへの接続に失敗しました" in response.data["error"]


@pytest.mark.api
class TestOneDriveCreateUploadSessionView:
    """OneDriveCreateUploadSessionViewのテストクラス"""

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_upload_session_success(
        self, mock_client_class, authenticated_client
    ):
        """アップロードセッションの作成が成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._create_upload_session.return_value = (
            "https://graph.microsoft.com/upload/session/123"
        )

        payload = {
            "file_name": "large_file.tar.gz",
            "file_size": 100000000,
            "folder_path": "/backup",
        }

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
        assert response.data["folder_path"] == "/backup"

        mock_client._create_upload_session.assert_called_once_with(
            file_name="large_file.tar.gz", folder_path="/backup"
        )

    def test_create_upload_session_without_authentication_fails(self, api_client):
        """認証なしでアップロードセッション作成が失敗すること"""
        payload = {
            "file_name": "large_file.tar.gz",
            "file_size": 100000000,
        }

        response = api_client.post("/onedrive/upload-session/", payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_upload_session_without_file_name_fails(self, authenticated_client):
        """ファイル名なしでセッション作成が失敗すること"""
        payload = {
            "file_size": 100000000,
        }

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file_name" in response.data

    def test_create_upload_session_without_file_size_fails(self, authenticated_client):
        """ファイルサイズなしでセッション作成が失敗すること"""
        payload = {
            "file_name": "large_file.tar.gz",
        }

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file_size" in response.data

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_upload_session_with_configuration_error(
        self, mock_client_class, authenticated_client
    ):
        """設定エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import ConfigurationError

        mock_client_class.side_effect = ConfigurationError("Missing configuration")

        payload = {
            "file_name": "large_file.tar.gz",
            "file_size": 100000000,
        }

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "サービスの設定に問題があります" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_upload_session_with_authentication_error(
        self, mock_client_class, authenticated_client
    ):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._create_upload_session.side_effect = AuthenticationError(
            "Token expired"
        )

        payload = {
            "file_name": "large_file.tar.gz",
            "file_size": 100000000,
        }

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "OneDriveへの認証に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_upload_session_with_upload_error(
        self, mock_client_class, authenticated_client
    ):
        """アップロードエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.onedrive.exceptions import UploadError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._create_upload_session.side_effect = UploadError(
            "Failed to create session"
        )

        payload = {
            "file_name": "large_file.tar.gz",
            "file_size": 100000000,
        }

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Failed to create session"

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_upload_session_with_network_error(
        self, mock_client_class, authenticated_client
    ):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._create_upload_session.side_effect = NetworkError(
            "Connection timeout"
        )

        payload = {
            "file_name": "large_file.tar.gz",
            "file_size": 100000000,
        }

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "OneDriveへの接続に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_upload_session_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に適切なエラーレスポンスを返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._create_upload_session.side_effect = Exception("Unexpected error")

        payload = {
            "file_name": "large_file.tar.gz",
            "file_size": 100000000,
        }

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert (
            "アップロードセッションの作成中に問題が発生しました"
            in response.data["error"]
        )

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_create_upload_session_with_default_folder_path(
        self, mock_client_class, authenticated_client
    ):
        """フォルダパスが指定されない場合、デフォルトでルートになること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._create_upload_session.return_value = (
            "https://graph.microsoft.com/upload/session/123"
        )

        payload = {
            "file_name": "large_file.tar.gz",
            "file_size": 100000000,
        }

        response = authenticated_client.post(
            "/onedrive/upload-session/", payload, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["folder_path"] == "/"

        mock_client._create_upload_session.assert_called_once_with(
            file_name="large_file.tar.gz", folder_path="/"
        )


@pytest.mark.api
class TestOneDriveUploadChunkView:
    """OneDriveUploadChunkViewのテストクラス"""

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_chunk_in_progress(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """チャンクアップロードが継続中の場合、200を返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._upload_chunk.return_value = {
            "nextExpectedRanges": ["10485760-"],
        }

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

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
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

    def test_upload_chunk_without_upload_url_fails(
        self, authenticated_client, mock_file
    ):
        """upload_urlなしでアップロードが失敗すること"""
        payload = {
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }

        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "upload_url" in response.data

    def test_upload_chunk_without_chunk_fails(self, authenticated_client):
        """chunkなしでアップロードが失敗すること"""
        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "offset": 0,
            "total_size": 100000000,
        }

        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "chunk" in response.data

    def test_upload_chunk_without_offset_fails(self, authenticated_client, mock_file):
        """offsetなしでアップロードが失敗すること"""
        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "total_size": 100000000,
        }

        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "offset" in response.data

    def test_upload_chunk_without_total_size_fails(
        self, authenticated_client, mock_file
    ):
        """total_sizeなしでアップロードが失敗すること"""
        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
        }

        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "total_size" in response.data

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_chunk_with_configuration_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """設定エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import ConfigurationError

        mock_client_class.side_effect = ConfigurationError("Missing configuration")

        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }

        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "サービスの設定に問題があります" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_chunk_with_authentication_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._upload_chunk.side_effect = AuthenticationError("Token expired")

        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }

        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "OneDriveへの認証に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_chunk_with_upload_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """アップロードエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.onedrive.exceptions import UploadError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._upload_chunk.side_effect = UploadError("Chunk upload failed")

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

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_chunk_with_network_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from integrations.msgraph.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._upload_chunk.side_effect = NetworkError("Connection timeout")

        payload = {
            "upload_url": "https://graph.microsoft.com/upload/session/123",
            "chunk": mock_file,
            "offset": 0,
            "total_size": 100000000,
        }

        response = authenticated_client.put(
            "/onedrive/upload-chunk/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "OneDriveへの接続に失敗しました" in response.data["error"]

    @patch("integrations.onedrive.views.OneDriveMSGraphClient")
    def test_upload_chunk_with_unexpected_error(
        self, mock_client_class, authenticated_client, mock_file
    ):
        """予期しないエラー時に適切なエラーレスポンスを返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client._upload_chunk.side_effect = Exception("Unexpected error")

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
