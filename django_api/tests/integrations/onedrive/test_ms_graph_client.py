"""MSGraphClientのテスト"""

from unittest.mock import Mock, patch

import pytest
import requests

from integrations.msgraph import OneDriveMSGraphClient
from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.msgraph.onedrive import (
    CHUNK_SIZE,
    SIMPLE_UPLOAD_THRESHOLD,
)
from integrations.onedrive.exceptions import (
    FolderOperationError,
    ListOperationError,
    UploadError,
)


def _make_http_error_response(status_code):
    """指定のHTTPステータスで raise_for_status が HTTPError を発生させる Mock を生成"""
    response = Mock()
    response.status_code = status_code
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=response
    )
    return response


@pytest.mark.unit
class TestOneDriveMSGraphClientInitialization:
    """OneDriveMSGraphClientの初期化テスト"""

    def test_successful_initialization(self, mock_ms_graph_settings):
        """正常に初期化できること"""
        client = OneDriveMSGraphClient()

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

    @pytest.mark.parametrize(
        "missing_label",
        [
            "テナントID",
            "クライアントID",
            "証明書サムプリント",
            "秘密鍵",
            "対象ユーザー",
            "データベースに存在しません",
        ],
    )
    def test_initialization_missing_setting_raises(self, missing_label):
        """設定が不足している場合 ConfigurationError になること"""
        with patch("integrations.msgraph.base.get_ms_graph_settings") as mock_get:
            mock_get.side_effect = ConfigurationError(missing_label)
            with pytest.raises(ConfigurationError) as excinfo:
                OneDriveMSGraphClient()
            assert missing_label in str(excinfo.value)


@pytest.mark.unit
class TestOneDriveMSGraphClientToken:
    """トークン取得関連のテスト"""

    @patch("integrations.msgraph.base.ConfidentialClientApplication")
    def test_acquire_token_success(self, mock_msal, ms_graph_client):
        """トークン取得が成功すること"""
        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "test-token-123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

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

    @patch("integrations.msgraph.base.ConfidentialClientApplication")
    def test_acquire_token_failure(self, mock_msal, ms_graph_client):
        """トークン取得が失敗した場合 AuthenticationError になること"""
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

    @patch("integrations.msgraph.base.ConfidentialClientApplication")
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
class TestOneDriveMSGraphClientUpload:
    """ファイルアップロード関連のテスト"""

    def test_upload_file_success(self, ms_graph_client):
        """ファイルアップロードが成功すること（小さいファイル → simple upload）"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "test.txt",
            "size": 1024,
            "web_url": "https://example.sharepoint.com/test.txt",
        }
        ms_graph_client._session.put = Mock(return_value=mock_response)

        result = ms_graph_client.upload_file_to_onedrive(
            file_content=b"test content",
            file_name="test.txt",
            folder_path="/documents",
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

    @patch("integrations.msgraph.base.ConfidentialClientApplication")
    def test_upload_file_token_expired_retry(self, mock_msal, ms_graph_client):
        """トークン切れ時に再取得してリトライすること"""
        mock_response_401 = Mock()
        mock_response_401.status_code = 401

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"name": "test.txt"}
        mock_response_200.raise_for_status = Mock()

        ms_graph_client._session.put = Mock(
            side_effect=[mock_response_401, mock_response_200]
        )

        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {"access_token": "new-token"}

        result = ms_graph_client.upload_file_to_onedrive(
            file_content=b"test content", file_name="test.txt"
        )

        assert result["name"] == "test.txt"
        assert ms_graph_client._session.put.call_count == 2

    @pytest.mark.parametrize(
        "side_effect, expected_exc, expected_msg",
        [
            pytest.param(
                requests.exceptions.Timeout(),
                NetworkError,
                "タイムアウト",
                id="timeout",
            ),
            pytest.param(
                requests.exceptions.ConnectionError(),
                NetworkError,
                "接続",
                id="connection_error",
            ),
        ],
    )
    def test_upload_file_network_errors(
        self, ms_graph_client, side_effect, expected_exc, expected_msg
    ):
        """ネットワーク系エラー時に NetworkError になること"""
        ms_graph_client._session.put = Mock(side_effect=side_effect)

        with pytest.raises(expected_exc) as excinfo:
            ms_graph_client.upload_file_to_onedrive(
                file_content=b"test content", file_name="test.txt"
            )
        assert expected_msg in str(excinfo.value)

    @pytest.mark.parametrize(
        "status_code, expected_msg",
        [
            (404, "フォルダが見つかりません"),
            (507, "容量"),
            (413, "大きすぎ"),
            (500, None),
        ],
        ids=["not_found", "insufficient_storage", "too_large", "generic_500"],
    )
    def test_upload_file_http_errors(self, ms_graph_client, status_code, expected_msg):
        """HTTP エラー時に UploadError になること"""
        ms_graph_client._session.put = Mock(
            return_value=_make_http_error_response(status_code)
        )

        with pytest.raises(UploadError) as excinfo:
            ms_graph_client.upload_file_to_onedrive(
                file_content=b"test content", file_name="test.txt"
            )
        if expected_msg is not None:
            assert expected_msg in str(excinfo.value)


@pytest.mark.unit
class TestOneDriveMSGraphClientLargeFileUpload:
    """大きなファイルのアップロードテスト"""

    def test_large_file_uses_upload_session(self, ms_graph_client):
        """大きいファイルはアップロードセッションを使用すること（成功シナリオ）"""
        ms_graph_client._session.post = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {"uploadUrl": "https://upload.example.com/session123"},
            )
        )
        ms_graph_client._session.put = Mock(
            return_value=Mock(
                status_code=201,
                json=lambda: {"id": "file-id-123", "name": "large.bin"},
            )
        )

        large_content = b"x" * (SIMPLE_UPLOAD_THRESHOLD + 1)
        result = ms_graph_client.upload_file_to_onedrive(
            file_content=large_content, file_name="large.bin"
        )

        assert result["id"] == "file-id-123"
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

    @pytest.mark.parametrize(
        "status_code, expected_exc, expected_msg",
        [
            (401, AuthenticationError, None),
            (404, UploadError, "フォルダが見つかりません"),
        ],
        ids=["auth_error", "folder_not_found"],
    )
    def test_create_upload_session_http_errors(
        self, ms_graph_client, status_code, expected_exc, expected_msg
    ):
        """セッション作成時の HTTP エラー"""
        ms_graph_client._session.post = Mock(
            return_value=_make_http_error_response(status_code)
        )

        with pytest.raises(expected_exc) as excinfo:
            ms_graph_client._create_upload_session("test.bin", "/uploads")
        if expected_msg is not None:
            assert expected_msg in str(excinfo.value)

    @pytest.mark.parametrize(
        "status_code, expected_keys",
        [
            (202, ["nextExpectedRanges"]),
            (201, ["id", "name"]),
        ],
        ids=["in_progress", "complete"],
    )
    def test_upload_chunk_success(self, ms_graph_client, status_code, expected_keys):
        """チャンクアップロードが成功すること（継続/完了）"""
        mock_response = Mock()
        mock_response.status_code = status_code
        if status_code == 202:
            mock_response.json.return_value = {"nextExpectedRanges": ["10485760-"]}
        else:
            mock_response.json.return_value = {"id": "file-id", "name": "completed.bin"}
        ms_graph_client._session.put = Mock(return_value=mock_response)

        result = ms_graph_client._upload_chunk(
            "https://upload.example.com/session",
            b"x" * CHUNK_SIZE,
            0,
            CHUNK_SIZE * 2,
        )

        for key in expected_keys:
            assert key in result

    @patch("time.sleep")
    def test_upload_chunk_retry_on_failure(self, mock_sleep, ms_graph_client):
        """チャンクアップロード失敗時にリトライすること"""
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
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    def test_upload_chunk_max_retries_exceeded(self, mock_sleep, ms_graph_client):
        """リトライ上限を超えた場合 UploadError になること"""
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

    def test_upload_large_file_timeout(self, ms_graph_client):
        """大きなファイルのアップロード中にタイムアウトした場合 NetworkError になること"""
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
class TestOneDriveMSGraphClientFolder:
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
        """フォルダ作成タイムアウト時に NetworkError になること"""
        ms_graph_client._session.post = Mock(side_effect=requests.exceptions.Timeout())

        with pytest.raises(NetworkError) as excinfo:
            ms_graph_client.create_folder("folder", "/")
        assert "タイムアウト" in str(excinfo.value)

    @pytest.mark.parametrize(
        "status_code, expected_exc, expected_msg",
        [
            (401, AuthenticationError, None),
            (404, FolderOperationError, "親フォルダ"),
            (409, FolderOperationError, "既に存在"),
        ],
        ids=["auth_error", "parent_not_found", "already_exists"],
    )
    def test_create_folder_http_errors(
        self, ms_graph_client, status_code, expected_exc, expected_msg
    ):
        """フォルダ作成時の HTTP エラー"""
        ms_graph_client._session.post = Mock(
            return_value=_make_http_error_response(status_code)
        )

        with pytest.raises(expected_exc) as excinfo:
            ms_graph_client.create_folder("folder", "/")
        if expected_msg is not None:
            assert expected_msg in str(excinfo.value)


@pytest.mark.unit
class TestOneDriveMSGraphClientList:
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
        """ファイル一覧取得タイムアウト時に NetworkError になること"""
        ms_graph_client._session.get = Mock(side_effect=requests.exceptions.Timeout())

        with pytest.raises(NetworkError) as excinfo:
            ms_graph_client.list_files("/")
        assert "タイムアウト" in str(excinfo.value)

    @pytest.mark.parametrize(
        "status_code, expected_exc, expected_msg",
        [
            (401, AuthenticationError, None),
            (404, ListOperationError, "見つかりません"),
            (500, ListOperationError, None),
        ],
        ids=["auth_error", "not_found", "generic_error"],
    )
    def test_list_files_http_errors(
        self, ms_graph_client, status_code, expected_exc, expected_msg
    ):
        """ファイル一覧取得時の HTTP エラー"""
        ms_graph_client._session.get = Mock(
            return_value=_make_http_error_response(status_code)
        )

        with pytest.raises(expected_exc) as excinfo:
            ms_graph_client.list_files("/")
        if expected_msg is not None:
            assert expected_msg in str(excinfo.value)
