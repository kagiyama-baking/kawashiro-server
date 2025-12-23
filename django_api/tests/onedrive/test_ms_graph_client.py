"""MSGraphClientのテスト"""

from unittest.mock import Mock, patch

import pytest
import requests

from ms_graph.exceptions import AuthenticationError, ConfigurationError, NetworkError
from onedrive.exceptions import (
    FolderOperationError,
    ListOperationError,
    UploadError,
)
from onedrive.ms_graph_client import (
    CHUNK_SIZE,
    SIMPLE_UPLOAD_THRESHOLD,
    MSGraphClient,
)


@pytest.mark.unit
class TestMSGraphClientInitialization:
    """MSGraphClientの初期化テスト"""

    def test_successful_initialization(self, mock_ms_graph_settings):
        """正常に初期化できること"""
        client = MSGraphClient()

        assert client.tenant_id == "test-tenant"
        assert client.client_id == "test-client"
        assert client.thumbprint == "test-thumb"
        assert (
            client._private_key
            == "-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----"
        )
        assert client.target_user == "test@example.com"
        assert client.authority == "https://login.microsoftonline.com/test-tenant"
        assert client.scopes == ["https://graph.microsoft.com/.default"]
        assert client.graph_url == "https://graph.microsoft.com/v1.0"

    def test_missing_tenant_id(self):
        """テナントIDが未設定の場合エラーになること"""
        with patch("onedrive.ms_graph_client.get_ms_graph_settings") as mock_get:
            mock_get.side_effect = ConfigurationError("テナントID")
            with pytest.raises(ConfigurationError) as excinfo:
                MSGraphClient()
            assert "テナントID" in str(excinfo.value)

    def test_missing_client_id(self):
        """クライアントIDが未設定の場合エラーになること"""
        with patch("onedrive.ms_graph_client.get_ms_graph_settings") as mock_get:
            mock_get.side_effect = ConfigurationError("クライアントID")
            with pytest.raises(ConfigurationError) as excinfo:
                MSGraphClient()
            assert "クライアントID" in str(excinfo.value)

    def test_missing_thumbprint(self):
        """サムプリントが未設定の場合エラーになること"""
        with patch("onedrive.ms_graph_client.get_ms_graph_settings") as mock_get:
            mock_get.side_effect = ConfigurationError("証明書サムプリント")
            with pytest.raises(ConfigurationError) as excinfo:
                MSGraphClient()
            assert "証明書サムプリント" in str(excinfo.value)

    def test_missing_key_file(self):
        """秘密鍵が未設定の場合エラーになること"""
        with patch("onedrive.ms_graph_client.get_ms_graph_settings") as mock_get:
            mock_get.side_effect = ConfigurationError("秘密鍵")
            with pytest.raises(ConfigurationError) as excinfo:
                MSGraphClient()
            assert "秘密鍵" in str(excinfo.value)

    def test_missing_target_user(self):
        """TARGET_USERが未設定の場合エラーになること"""
        with patch("onedrive.ms_graph_client.get_ms_graph_settings") as mock_get:
            mock_get.side_effect = ConfigurationError("対象ユーザー")
            with pytest.raises(ConfigurationError) as excinfo:
                MSGraphClient()
            assert "対象ユーザー" in str(excinfo.value)

    def test_key_file_not_exists(self):
        """設定がDBにない場合エラーになること"""
        with patch("onedrive.ms_graph_client.get_ms_graph_settings") as mock_get:
            mock_get.side_effect = ConfigurationError("データベースに存在しません")
            with pytest.raises(ConfigurationError) as excinfo:
                MSGraphClient()
            assert "データベースに存在しません" in str(excinfo.value)


@pytest.mark.unit
class TestMSGraphClientToken:
    """トークン取得関連のテスト"""

    @patch("onedrive.ms_graph_client.ConfidentialClientApplication")
    def test_acquire_token_success(self, mock_msal, ms_graph_client):
        """トークン取得が成功すること"""
        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "test-token-123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        # トークンをリセットしてテスト
        ms_graph_client._access_token = None
        token = ms_graph_client.acquire_token()

        assert token == "test-token-123"
        assert ms_graph_client._access_token == "test-token-123"

        mock_msal.assert_called_once_with(
            "test-client",
            authority="https://login.microsoftonline.com/test-tenant",
            client_credential={
                "private_key": "-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----",
                "thumbprint": "test-thumb",
            },
        )
        mock_app.acquire_token_for_client.assert_called_once_with(
            ["https://graph.microsoft.com/.default"]
        )

    @patch("onedrive.ms_graph_client.ConfidentialClientApplication")
    def test_acquire_token_failure(self, mock_msal, ms_graph_client):
        """トークン取得が失敗した場合エラーになること"""
        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "Invalid client credentials",
        }

        ms_graph_client._access_token = None
        with pytest.raises(AuthenticationError) as excinfo:
            ms_graph_client.acquire_token()
        assert "Invalid client credentials" in str(excinfo.value)

    def test_get_headers_with_existing_token(self, ms_graph_client):
        """既存のトークンがある場合のヘッダー取得"""
        ms_graph_client._access_token = "existing-token"

        headers = ms_graph_client.get_headers()

        assert headers["Authorization"] == "Bearer existing-token"
        assert headers["Content-Type"] == "application/octet-stream"
        assert headers["Accept"] == "application/json"

    @patch("onedrive.ms_graph_client.ConfidentialClientApplication")
    def test_get_headers_without_token(self, mock_msal, ms_graph_client):
        """トークンがない場合は取得してからヘッダーを返すこと"""
        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "new-token-456",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        ms_graph_client._access_token = None
        headers = ms_graph_client.get_headers()

        assert headers["Authorization"] == "Bearer new-token-456"
        assert ms_graph_client._access_token == "new-token-456"
        mock_app.acquire_token_for_client.assert_called_once()


@pytest.mark.unit
class TestMSGraphClientUpload:
    """ファイルアップロード関連のテスト"""

    def test_upload_file_success(self, ms_graph_client):
        """ファイルアップロードが成功すること（小さいファイル）"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "test.txt",
            "size": 1024,
            "web_url": "https://example.sharepoint.com/test.txt",
        }
        ms_graph_client._session.put = Mock(return_value=mock_response)

        # 小さいファイルなのでシンプルアップロードが使われる
        result = ms_graph_client.upload_file_to_onedrive(
            file_content=b"test content", file_name="test.txt", folder_path="/documents"
        )

        assert result["name"] == "test.txt"

        expected_url = "https://graph.microsoft.com/v1.0/users/test@example.com/drive/root:/documents/test.txt:/content"
        ms_graph_client._session.put.assert_called_once_with(
            expected_url,
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/octet-stream",
                "Accept": "application/json",
            },
            data=b"test content",
            timeout=60,
        )

    def test_upload_file_with_root_path(self, ms_graph_client):
        """ルートパスへのファイルアップロード"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "test.txt"}
        ms_graph_client._session.put = Mock(return_value=mock_response)

        ms_graph_client.upload_file_to_onedrive(
            file_content=b"test content", file_name="test.txt", folder_path="/"
        )

        expected_url = "https://graph.microsoft.com/v1.0/users/test@example.com/drive/root:/test.txt:/content"
        assert ms_graph_client._session.put.call_args[0][0] == expected_url

    @patch("onedrive.ms_graph_client.ConfidentialClientApplication")
    def test_upload_file_token_expired_retry(self, mock_msal, ms_graph_client):
        """トークン切れ時に再取得してリトライすること"""
        # 最初の呼び出しは401、再試行で成功
        mock_response_401 = Mock()
        mock_response_401.status_code = 401

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"name": "test.txt"}
        mock_response_200.raise_for_status = Mock()

        ms_graph_client._session.put = Mock(
            side_effect=[mock_response_401, mock_response_200]
        )

        # トークン再取得のモック
        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "new-token",
        }

        result = ms_graph_client.upload_file_to_onedrive(
            file_content=b"test content", file_name="test.txt"
        )

        assert result["name"] == "test.txt"
        assert ms_graph_client._session.put.call_count == 2

    def test_upload_file_timeout(self, ms_graph_client):
        """タイムアウト時にNetworkErrorになること"""
        ms_graph_client._session.put = Mock(side_effect=requests.exceptions.Timeout())

        with pytest.raises(NetworkError) as excinfo:
            ms_graph_client.upload_file_to_onedrive(
                file_content=b"test content", file_name="test.txt"
            )
        assert "タイムアウト" in str(excinfo.value)

    def test_upload_file_connection_error(self, ms_graph_client):
        """接続エラー時にNetworkErrorになること"""
        ms_graph_client._session.put = Mock(
            side_effect=requests.exceptions.ConnectionError()
        )

        with pytest.raises(NetworkError) as excinfo:
            ms_graph_client.upload_file_to_onedrive(
                file_content=b"test content", file_name="test.txt"
            )
        assert "接続" in str(excinfo.value)

    def test_upload_file_not_found(self, ms_graph_client):
        """フォルダが見つからない場合UploadErrorになること"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.put = Mock(return_value=mock_response)

        with pytest.raises(UploadError) as excinfo:
            ms_graph_client.upload_file_to_onedrive(
                file_content=b"test content", file_name="test.txt"
            )
        assert "フォルダが見つかりません" in str(excinfo.value)

    def test_upload_file_insufficient_storage(self, ms_graph_client):
        """容量不足時にUploadErrorになること"""
        mock_response = Mock()
        mock_response.status_code = 507
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.put = Mock(return_value=mock_response)

        with pytest.raises(UploadError) as excinfo:
            ms_graph_client.upload_file_to_onedrive(
                file_content=b"test content", file_name="test.txt"
            )
        assert "容量" in str(excinfo.value)

    def test_upload_file_too_large(self, ms_graph_client):
        """ファイルが大きすぎる場合UploadErrorになること"""
        mock_response = Mock()
        mock_response.status_code = 413
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.put = Mock(return_value=mock_response)

        with pytest.raises(UploadError) as excinfo:
            ms_graph_client.upload_file_to_onedrive(
                file_content=b"test content", file_name="test.txt"
            )
        assert "大きすぎ" in str(excinfo.value)

    def test_upload_file_generic_http_error(self, ms_graph_client):
        """その他のHTTPエラー時にUploadErrorになること"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.put = Mock(return_value=mock_response)

        with pytest.raises(UploadError):
            ms_graph_client.upload_file_to_onedrive(
                file_content=b"test content", file_name="test.txt"
            )


@pytest.mark.unit
class TestMSGraphClientLargeFileUpload:
    """大きなファイルのアップロードテスト"""

    def test_small_file_uses_simple_upload(self, ms_graph_client):
        """小さいファイルはシンプルアップロードを使用すること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "small.txt"}
        ms_graph_client._session.put = Mock(return_value=mock_response)

        # 4MB未満のファイル
        small_content = b"x" * (SIMPLE_UPLOAD_THRESHOLD - 1)
        ms_graph_client.upload_file_to_onedrive(
            file_content=small_content, file_name="small.txt"
        )

        # シンプルアップロードのURL形式を確認
        assert ":/content" in ms_graph_client._session.put.call_args[0][0]

    def test_large_file_uses_upload_session(self, ms_graph_client):
        """大きいファイルはアップロードセッションを使用すること"""
        # セッション作成のモック
        mock_session_response = Mock()
        mock_session_response.status_code = 200
        mock_session_response.json.return_value = {
            "uploadUrl": "https://upload.example.com/session123"
        }
        ms_graph_client._session.post = Mock(return_value=mock_session_response)

        # チャンクアップロードのモック
        mock_chunk_response = Mock()
        mock_chunk_response.status_code = 201
        mock_chunk_response.json.return_value = {
            "id": "file-id-123",
            "name": "large.bin",
        }
        ms_graph_client._session.put = Mock(return_value=mock_chunk_response)

        # 4MB以上のファイル
        large_content = b"x" * (SIMPLE_UPLOAD_THRESHOLD + 1)
        result = ms_graph_client.upload_file_to_onedrive(
            file_content=large_content, file_name="large.bin"
        )

        assert result["id"] == "file-id-123"
        # セッション作成が呼ばれたことを確認
        assert "createUploadSession" in ms_graph_client._session.post.call_args[0][0]

    def test_create_upload_session_success(self, ms_graph_client):
        """アップロードセッション作成が成功すること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "uploadUrl": "https://upload.example.com/session123"
        }
        ms_graph_client._session.post = Mock(return_value=mock_response)

        url = ms_graph_client._create_upload_session("test.bin", "/uploads")

        assert url == "https://upload.example.com/session123"

    def test_create_upload_session_auth_error(self, ms_graph_client):
        """セッション作成時の認証エラー"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.post = Mock(return_value=mock_response)

        with pytest.raises(AuthenticationError):
            ms_graph_client._create_upload_session("test.bin", "/uploads")

    def test_create_upload_session_folder_not_found(self, ms_graph_client):
        """セッション作成時のフォルダ未検出エラー"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.post = Mock(return_value=mock_response)

        with pytest.raises(UploadError) as excinfo:
            ms_graph_client._create_upload_session("test.bin", "/uploads")
        assert "フォルダが見つかりません" in str(excinfo.value)

    def test_upload_chunk_success(self, ms_graph_client):
        """チャンクアップロードが成功すること（継続）"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"nextExpectedRanges": ["10485760-"]}
        ms_graph_client._session.put = Mock(return_value=mock_response)

        result = ms_graph_client._upload_chunk(
            "https://upload.example.com/session",
            b"x" * CHUNK_SIZE,
            0,
            CHUNK_SIZE * 2,
        )

        assert "nextExpectedRanges" in result

    def test_upload_chunk_complete(self, ms_graph_client):
        """チャンクアップロード完了時"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "file-id", "name": "completed.bin"}
        ms_graph_client._session.put = Mock(return_value=mock_response)

        result = ms_graph_client._upload_chunk(
            "https://upload.example.com/session",
            b"x" * 1000,
            CHUNK_SIZE,
            CHUNK_SIZE + 1000,
        )

        assert result["id"] == "file-id"

    @patch("time.sleep")
    def test_upload_chunk_retry_on_failure(self, mock_sleep, ms_graph_client):
        """チャンクアップロード失敗時にリトライすること"""
        # 最初の2回は失敗、3回目で成功
        ms_graph_client._session.put = Mock(
            side_effect=[
                requests.exceptions.RequestException("Network error"),
                requests.exceptions.RequestException("Network error"),
                Mock(status_code=202, json=lambda: {"nextExpectedRanges": []}),
            ]
        )

        ms_graph_client._upload_chunk(
            "https://upload.example.com/session",
            b"x" * 1000,
            0,
            2000,
        )

        assert ms_graph_client._session.put.call_count == 3
        assert mock_sleep.call_count == 2  # 2回リトライ

    @patch("time.sleep")
    def test_upload_chunk_max_retries_exceeded(self, mock_sleep, ms_graph_client):
        """リトライ上限を超えた場合エラーになること"""
        ms_graph_client._session.put = Mock(
            side_effect=requests.exceptions.RequestException("Network error")
        )

        with pytest.raises(UploadError):
            ms_graph_client._upload_chunk(
                "https://upload.example.com/session",
                b"x" * 1000,
                0,
                2000,
                max_retries=3,
            )

        assert ms_graph_client._session.put.call_count == 3

    def test_upload_large_file_success(self, ms_graph_client):
        """大きなファイルのアップロードが成功すること"""
        # セッション作成
        ms_graph_client._session.post = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {"uploadUrl": "https://upload.example.com/session"},
            )
        )

        # 最後のチャンクで完了を返す
        ms_graph_client._session.put = Mock(
            return_value=Mock(
                status_code=201, json=lambda: {"id": "file-id", "name": "large.bin"}
            )
        )

        large_content = b"x" * (SIMPLE_UPLOAD_THRESHOLD + 100)
        result = ms_graph_client.upload_file_to_onedrive(
            file_content=large_content, file_name="large.bin"
        )

        assert result["id"] == "file-id"

    def test_upload_large_file_timeout(self, ms_graph_client):
        """大きなファイルのアップロード中にタイムアウトした場合"""
        ms_graph_client._session.post = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {"uploadUrl": "https://upload.example.com/session"},
            )
        )
        ms_graph_client._session.put = Mock(side_effect=requests.exceptions.Timeout())

        large_content = b"x" * (SIMPLE_UPLOAD_THRESHOLD + 100)
        with pytest.raises(NetworkError) as excinfo:
            ms_graph_client.upload_file_to_onedrive(
                file_content=large_content, file_name="large.bin"
            )
        assert "タイムアウト" in str(excinfo.value)


@pytest.mark.unit
class TestMSGraphClientFolder:
    """フォルダ操作関連のテスト"""

    def test_create_folder_success(self, ms_graph_client):
        """フォルダ作成が成功すること"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "folder-id",
            "name": "new_folder",
            "folder": {},
        }
        ms_graph_client._session.post = Mock(return_value=mock_response)

        result = ms_graph_client.create_folder("new_folder", "/documents")

        assert result["name"] == "new_folder"

    def test_create_folder_at_root(self, ms_graph_client):
        """ルートにフォルダを作成できること"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"name": "root_folder"}
        ms_graph_client._session.post = Mock(return_value=mock_response)

        ms_graph_client.create_folder("root_folder", "/")

        expected_url = "https://graph.microsoft.com/v1.0/users/test@example.com/drive/root/children"
        assert ms_graph_client._session.post.call_args[0][0] == expected_url

    def test_create_folder_timeout(self, ms_graph_client):
        """フォルダ作成タイムアウト"""
        ms_graph_client._session.post = Mock(side_effect=requests.exceptions.Timeout())

        with pytest.raises(NetworkError) as excinfo:
            ms_graph_client.create_folder("folder", "/")
        assert "タイムアウト" in str(excinfo.value)

    def test_create_folder_auth_error(self, ms_graph_client):
        """フォルダ作成時の認証エラー"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.post = Mock(return_value=mock_response)

        with pytest.raises(AuthenticationError):
            ms_graph_client.create_folder("folder", "/")

    def test_create_folder_parent_not_found(self, ms_graph_client):
        """親フォルダが見つからない場合"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.post = Mock(return_value=mock_response)

        with pytest.raises(FolderOperationError) as excinfo:
            ms_graph_client.create_folder("folder", "/nonexistent")
        assert "親フォルダ" in str(excinfo.value)

    def test_create_folder_already_exists(self, ms_graph_client):
        """フォルダが既に存在する場合"""
        mock_response = Mock()
        mock_response.status_code = 409
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.post = Mock(return_value=mock_response)

        with pytest.raises(FolderOperationError) as excinfo:
            ms_graph_client.create_folder("existing", "/")
        assert "既に存在" in str(excinfo.value)


@pytest.mark.unit
class TestMSGraphClientList:
    """ファイル一覧取得関連のテスト"""

    def test_list_files_success(self, ms_graph_client):
        """ファイル一覧取得が成功すること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {"name": "file1.txt", "id": "1"},
                {"name": "file2.txt", "id": "2"},
            ]
        }
        ms_graph_client._session.get = Mock(return_value=mock_response)

        result = ms_graph_client.list_files("/documents")

        assert len(result) == 2
        assert result[0]["name"] == "file1.txt"

    def test_list_files_root(self, ms_graph_client):
        """ルートのファイル一覧取得"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": []}
        ms_graph_client._session.get = Mock(return_value=mock_response)

        ms_graph_client.list_files("/")

        expected_url = "https://graph.microsoft.com/v1.0/users/test@example.com/drive/root/children"
        assert ms_graph_client._session.get.call_args[0][0] == expected_url

    def test_list_files_timeout(self, ms_graph_client):
        """ファイル一覧取得タイムアウト"""
        ms_graph_client._session.get = Mock(side_effect=requests.exceptions.Timeout())

        with pytest.raises(NetworkError) as excinfo:
            ms_graph_client.list_files("/")
        assert "タイムアウト" in str(excinfo.value)

    def test_list_files_auth_error(self, ms_graph_client):
        """ファイル一覧取得時の認証エラー"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.get = Mock(return_value=mock_response)

        with pytest.raises(AuthenticationError):
            ms_graph_client.list_files("/")

    def test_list_files_not_found(self, ms_graph_client):
        """フォルダが見つからない場合"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.get = Mock(return_value=mock_response)

        with pytest.raises(ListOperationError) as excinfo:
            ms_graph_client.list_files("/nonexistent")
        assert "見つかりません" in str(excinfo.value)

    def test_list_files_generic_error(self, ms_graph_client):
        """その他のエラー"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        ms_graph_client._session.get = Mock(return_value=mock_response)

        with pytest.raises(ListOperationError):
            ms_graph_client.list_files("/")


@pytest.mark.unit
class TestMSGraphClientPerformanceOptimization:
    """パフォーマンス最適化関連のテスト"""

    def test_chunk_size_is_60mb(self):
        """チャンクサイズが60MB（最大値）であること"""
        # Graph APIの最大チャンクサイズは60MB
        expected_chunk_size = 60 * 1024 * 1024
        assert expected_chunk_size == CHUNK_SIZE

    def test_chunk_size_is_multiple_of_320kib(self):
        """チャンクサイズが320KiBの倍数であること（Graph API要件）"""
        # Graph APIはチャンクサイズが320KiBの倍数である必要がある
        assert CHUNK_SIZE % (320 * 1024) == 0

    def test_client_has_session_attribute(self, ms_graph_client):
        """クライアントがセッション属性を持つこと"""
        assert hasattr(ms_graph_client, "_session")
        assert ms_graph_client._session is not None

    def test_session_is_requests_session(self, ms_graph_client):
        """セッションがrequests.Sessionインスタンスであること"""
        import requests

        assert isinstance(ms_graph_client._session, requests.Session)

    def test_upload_chunk_uses_session(self, ms_graph_client):
        """チャンクアップロードがセッションを使用すること"""
        # セッションのputメソッドをモック
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"nextExpectedRanges": ["10485760-"]}
        ms_graph_client._session.put = Mock(return_value=mock_response)

        ms_graph_client._upload_chunk(
            "https://upload.example.com/session",
            b"x" * 1000,
            0,
            2000,
        )

        # セッションのputが呼ばれたことを確認
        ms_graph_client._session.put.assert_called_once()

    def test_simple_upload_uses_session(self, ms_graph_client):
        """シンプルアップロードがセッションを使用すること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "test.txt"}
        ms_graph_client._session.put = Mock(return_value=mock_response)

        ms_graph_client._simple_upload(b"test content", "test.txt", "/")

        ms_graph_client._session.put.assert_called_once()

    def test_create_upload_session_uses_session(self, ms_graph_client):
        """アップロードセッション作成がセッションを使用すること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "uploadUrl": "https://upload.example.com/session123"
        }
        ms_graph_client._session.post = Mock(return_value=mock_response)

        ms_graph_client._create_upload_session("test.bin", "/uploads")

        ms_graph_client._session.post.assert_called_once()
