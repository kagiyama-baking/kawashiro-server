"""MSGraphClientのテスト"""
import os
import pytest
from unittest.mock import Mock, patch, mock_open, MagicMock
from django.test import override_settings
from onedrive.ms_graph_client import MSGraphClient
from onedrive.exceptions import (
    ConfigurationError,
    AuthenticationError,
    UploadError,
    FolderOperationError,
    ListOperationError,
    NetworkError
)
import requests


@pytest.mark.unit
class TestMSGraphClientInitialization:
    """MSGraphClientの初期化テスト"""

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER='test@example.com'
    )
    @patch('os.path.exists')
    def test_successful_initialization(self, mock_exists):
        """正常に初期化できること"""
        mock_exists.return_value = True

        client = MSGraphClient()

        assert client.tenant_id == 'test-tenant'
        assert client.client_id == 'test-client'
        assert client.thumbprint == 'test-thumb'
        assert client.key_file == '/path/to/key.pem'
        assert client.target_user == 'test@example.com'
        assert client.authority == 'https://login.microsoftonline.com/test-tenant'
        assert client.scopes == ['https://graph.microsoft.com/.default']
        assert client.graph_url == 'https://graph.microsoft.com/v1.0'

    @override_settings(
        AZURE_TENANT_ID='',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER='test@example.com'
    )
    def test_missing_tenant_id(self):
        """TENANT_IDが未設定の場合エラーになること"""
        with pytest.raises(ConfigurationError) as excinfo:
            MSGraphClient()
        assert 'AZURE_TENANT_ID' in str(excinfo.value)

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER='test@example.com'
    )
    def test_missing_client_id(self):
        """CLIENT_IDが未設定の場合エラーになること"""
        with pytest.raises(ConfigurationError) as excinfo:
            MSGraphClient()
        assert 'AZURE_CLIENT_ID' in str(excinfo.value)

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER='test@example.com'
    )
    def test_missing_thumbprint(self):
        """THUMBPRINTが未設定の場合エラーになること"""
        with pytest.raises(ConfigurationError) as excinfo:
            MSGraphClient()
        assert 'AZURE_CERT_THUMBPRINT' in str(excinfo.value)

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='',
        TARGET_USER='test@example.com'
    )
    def test_missing_key_file(self):
        """KEY_FILEが未設定の場合エラーになること"""
        with pytest.raises(ConfigurationError) as excinfo:
            MSGraphClient()
        assert 'AZURE_CERT_KEY_FILE' in str(excinfo.value)

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER=''
    )
    def test_missing_target_user(self):
        """TARGET_USERが未設定の場合エラーになること"""
        with pytest.raises(ConfigurationError) as excinfo:
            MSGraphClient()
        assert 'TARGET_USER' in str(excinfo.value)

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/nonexistent/key.pem',
        TARGET_USER='test@example.com'
    )
    @patch('os.path.exists')
    def test_key_file_not_exists(self, mock_exists):
        """秘密鍵ファイルが存在しない場合エラーになること"""
        mock_exists.return_value = False

        with pytest.raises(ConfigurationError) as excinfo:
            MSGraphClient()
        assert '秘密鍵ファイルが見つかりません' in str(excinfo.value)


@pytest.mark.unit
class TestMSGraphClientToken:
    """トークン取得関連のテスト"""

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER='test@example.com'
    )
    @patch('os.path.exists')
    def setup_method(self, method, mock_exists):
        """テストセットアップ"""
        mock_exists.return_value = True
        self.client = MSGraphClient()

    @patch('onedrive.ms_graph_client.ConfidentialClientApplication')
    @patch('builtins.open', new_callable=mock_open, read_data=b'-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----')
    def test_acquire_token_success(self, mock_file, mock_msal):
        """トークン取得が成功すること"""
        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {
            'access_token': 'test-token-123',
            'token_type': 'Bearer',
            'expires_in': 3600
        }

        token = self.client.acquire_token()

        assert token == 'test-token-123'
        assert self.client._access_token == 'test-token-123'

        mock_msal.assert_called_once_with(
            'test-client',
            authority='https://login.microsoftonline.com/test-tenant',
            client_credential={
                'private_key': '-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----',
                'thumbprint': 'test-thumb'
            }
        )
        mock_app.acquire_token_for_client.assert_called_once_with(['https://graph.microsoft.com/.default'])

    @patch('onedrive.ms_graph_client.ConfidentialClientApplication')
    @patch('builtins.open', new_callable=mock_open, read_data=b'-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----')
    def test_acquire_token_failure(self, mock_file, mock_msal):
        """トークン取得が失敗した場合エラーになること"""
        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {
            'error': 'invalid_client',
            'error_description': 'Invalid client credentials'
        }

        with pytest.raises(AuthenticationError) as excinfo:
            self.client.acquire_token()
        assert 'Invalid client credentials' in str(excinfo.value)

    @patch('msal.ConfidentialClientApplication')
    @patch('builtins.open', new_callable=mock_open, read_data=b'-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----')
    def test_get_headers_with_existing_token(self, mock_file, mock_msal):
        """既存のトークンがある場合のヘッダー取得"""
        self.client._access_token = 'existing-token'

        headers = self.client.get_headers()

        assert headers['Authorization'] == 'Bearer existing-token'
        assert headers['Content-Type'] == 'application/octet-stream'
        assert headers['Accept'] == 'application/json'
        mock_msal.assert_not_called()

    @patch('onedrive.ms_graph_client.ConfidentialClientApplication')
    @patch('builtins.open', new_callable=mock_open, read_data=b'-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----')
    def test_get_headers_without_token(self, mock_file, mock_msal):
        """トークンがない場合は取得してからヘッダーを返すこと"""
        mock_app = Mock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {
            'access_token': 'new-token-456',
            'token_type': 'Bearer',
            'expires_in': 3600
        }

        headers = self.client.get_headers()

        assert headers['Authorization'] == 'Bearer new-token-456'
        assert self.client._access_token == 'new-token-456'
        mock_app.acquire_token_for_client.assert_called_once()


@pytest.mark.unit
class TestMSGraphClientUpload:
    """ファイルアップロード関連のテスト"""

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER='test@example.com'
    )
    @patch('os.path.exists')
    def setup_method(self, method, mock_exists):
        """テストセットアップ"""
        mock_exists.return_value = True
        self.client = MSGraphClient()
        self.client._access_token = 'test-token'

    @patch('requests.put')
    def test_upload_file_success(self, mock_put):
        """ファイルアップロードが成功すること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'name': 'test.txt',
            'size': 1024,
            'web_url': 'https://example.sharepoint.com/test.txt'
        }
        mock_put.return_value = mock_response

        result = self.client.upload_file_to_onedrive(
            file_content=b'test content',
            file_name='test.txt',
            folder_path='/documents'
        )

        assert result['name'] == 'test.txt'

        expected_url = 'https://graph.microsoft.com/v1.0/users/test@example.com/drive/root:/documents/test.txt:/content'
        mock_put.assert_called_once_with(
            expected_url,
            headers={
                'Authorization': 'Bearer test-token',
                'Content-Type': 'application/octet-stream',
                'Accept': 'application/json'
            },
            data=b'test content',
            timeout=60
        )

    @patch('requests.put')
    def test_upload_file_with_root_path(self, mock_put):
        """ルートパスへのファイルアップロード"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'name': 'test.txt'}
        mock_put.return_value = mock_response

        self.client.upload_file_to_onedrive(
            file_content=b'test content',
            file_name='test.txt',
            folder_path='/'
        )

        expected_url = 'https://graph.microsoft.com/v1.0/users/test@example.com/drive/root:/test.txt:/content'
        mock_put.assert_called_once()
        assert mock_put.call_args[0][0] == expected_url

    @patch('requests.put')
    def test_upload_file_token_expired_retry(self, mock_put):
        """トークン期限切れ時に再取得してリトライすること"""
        mock_response_401 = Mock()
        mock_response_401.status_code = 401
        mock_response_401.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response_401)

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'name': 'test.txt'}

        mock_put.side_effect = [mock_response_401, mock_response_200]

        with patch.object(self.client, 'acquire_token') as mock_acquire:
            mock_acquire.return_value = 'new-token'

            result = self.client.upload_file_to_onedrive(
                file_content=b'test content',
                file_name='test.txt'
            )

            assert result['name'] == 'test.txt'
            mock_acquire.assert_called_once()
            assert mock_put.call_count == 2

    @patch('requests.put')
    def test_upload_file_timeout(self, mock_put):
        """タイムアウト時にNetworkErrorが発生すること"""
        mock_put.side_effect = requests.exceptions.Timeout()

        with pytest.raises(NetworkError) as excinfo:
            self.client.upload_file_to_onedrive(
                file_content=b'test content',
                file_name='test.txt'
            )
        assert 'タイムアウト' in str(excinfo.value)

    @patch('requests.put')
    def test_upload_file_connection_error(self, mock_put):
        """接続エラー時にNetworkErrorが発生すること"""
        mock_put.side_effect = requests.exceptions.ConnectionError()

        with pytest.raises(NetworkError) as excinfo:
            self.client.upload_file_to_onedrive(
                file_content=b'test content',
                file_name='test.txt'
            )
        assert '接続に失敗' in str(excinfo.value)

    @patch('requests.put')
    def test_upload_file_not_found(self, mock_put):
        """404エラー時にUploadErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_put.return_value = mock_response

        with pytest.raises(UploadError) as excinfo:
            self.client.upload_file_to_onedrive(
                file_content=b'test content',
                file_name='test.txt'
            )
        assert 'フォルダが見つかりません' in str(excinfo.value)

    @patch('requests.put')
    def test_upload_file_insufficient_storage(self, mock_put):
        """507エラー時にUploadErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 507
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_put.return_value = mock_response

        with pytest.raises(UploadError) as excinfo:
            self.client.upload_file_to_onedrive(
                file_content=b'test content',
                file_name='test.txt'
            )
        assert '容量が不足' in str(excinfo.value)

    @patch('requests.put')
    def test_upload_file_too_large(self, mock_put):
        """413エラー時にUploadErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 413
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_put.return_value = mock_response

        with pytest.raises(UploadError) as excinfo:
            self.client.upload_file_to_onedrive(
                file_content=b'test content',
                file_name='test.txt'
            )
        assert 'ファイルサイズが大きすぎます' in str(excinfo.value)

    @patch('requests.put')
    def test_upload_file_generic_http_error(self, mock_put):
        """その他のHTTPエラー時にUploadErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_put.return_value = mock_response

        with pytest.raises(UploadError) as excinfo:
            self.client.upload_file_to_onedrive(
                file_content=b'test content',
                file_name='test.txt'
            )
        assert 'アップロードに失敗' in str(excinfo.value)


@pytest.mark.unit
class TestMSGraphClientFolder:
    """フォルダ操作関連のテスト"""

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER='test@example.com'
    )
    @patch('os.path.exists')
    def setup_method(self, method, mock_exists):
        """テストセットアップ"""
        mock_exists.return_value = True
        self.client = MSGraphClient()
        self.client._access_token = 'test-token'

    @patch('requests.post')
    def test_create_folder_success(self, mock_post):
        """フォルダ作成が成功すること"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'name': 'NewFolder',
            'folder': {},
            'web_url': 'https://example.sharepoint.com/NewFolder'
        }
        mock_post.return_value = mock_response

        result = self.client.create_folder(
            folder_name='NewFolder',
            parent_path='/documents'
        )

        assert result['name'] == 'NewFolder'

        expected_url = 'https://graph.microsoft.com/v1.0/users/test@example.com/drive/root:/documents:/children'
        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == expected_url
        assert mock_post.call_args[1]['json']['name'] == 'NewFolder'

    @patch('requests.post')
    def test_create_folder_at_root(self, mock_post):
        """ルートへのフォルダ作成"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'name': 'NewFolder'}
        mock_post.return_value = mock_response

        self.client.create_folder(
            folder_name='NewFolder',
            parent_path='/'
        )

        expected_url = 'https://graph.microsoft.com/v1.0/users/test@example.com/drive/root/children'
        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == expected_url

    @patch('requests.post')
    def test_create_folder_timeout(self, mock_post):
        """タイムアウト時にNetworkErrorが発生すること"""
        mock_post.side_effect = requests.exceptions.Timeout()

        with pytest.raises(NetworkError) as excinfo:
            self.client.create_folder('NewFolder')
        assert 'タイムアウト' in str(excinfo.value)

    @patch('requests.post')
    def test_create_folder_auth_error(self, mock_post):
        """401エラー時にAuthenticationErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        with pytest.raises(AuthenticationError) as excinfo:
            self.client.create_folder('NewFolder')
        assert '認証に失敗' in str(excinfo.value)

    @patch('requests.post')
    def test_create_folder_parent_not_found(self, mock_post):
        """404エラー時にFolderOperationErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        with pytest.raises(FolderOperationError) as excinfo:
            self.client.create_folder('NewFolder')
        assert '親フォルダが見つかりません' in str(excinfo.value)

    @patch('requests.post')
    def test_create_folder_already_exists(self, mock_post):
        """409エラー時にFolderOperationErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 409
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        with pytest.raises(FolderOperationError) as excinfo:
            self.client.create_folder('ExistingFolder')
        assert '既に存在' in str(excinfo.value)


@pytest.mark.unit
class TestMSGraphClientList:
    """ファイル一覧取得関連のテスト"""

    @override_settings(
        AZURE_TENANT_ID='test-tenant',
        AZURE_CLIENT_ID='test-client',
        AZURE_CERT_THUMBPRINT='test-thumb',
        AZURE_CERT_KEY_FILE='/path/to/key.pem',
        TARGET_USER='test@example.com'
    )
    @patch('os.path.exists')
    def setup_method(self, method, mock_exists):
        """テストセットアップ"""
        mock_exists.return_value = True
        self.client = MSGraphClient()
        self.client._access_token = 'test-token'

    @patch('requests.get')
    def test_list_files_success(self, mock_get):
        """ファイル一覧取得が成功すること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'value': [
                {'name': 'file1.txt', 'size': 1024},
                {'name': 'file2.pdf', 'size': 2048},
                {'name': 'folder1', 'folder': {}}
            ]
        }
        mock_get.return_value = mock_response

        result = self.client.list_files(folder_path='/documents')

        assert len(result) == 3
        assert result[0]['name'] == 'file1.txt'

        expected_url = 'https://graph.microsoft.com/v1.0/users/test@example.com/drive/root:/documents:/children'
        mock_get.assert_called_once()
        assert mock_get.call_args[0][0] == expected_url

    @patch('requests.get')
    def test_list_files_root(self, mock_get):
        """ルートディレクトリのファイル一覧取得"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'value': []}
        mock_get.return_value = mock_response

        result = self.client.list_files('/')

        assert result == []

        expected_url = 'https://graph.microsoft.com/v1.0/users/test@example.com/drive/root/children'
        mock_get.assert_called_once()
        assert mock_get.call_args[0][0] == expected_url

    @patch('requests.get')
    def test_list_files_timeout(self, mock_get):
        """タイムアウト時にNetworkErrorが発生すること"""
        mock_get.side_effect = requests.exceptions.Timeout()

        with pytest.raises(NetworkError) as excinfo:
            self.client.list_files()
        assert 'タイムアウト' in str(excinfo.value)

    @patch('requests.get')
    def test_list_files_auth_error(self, mock_get):
        """401エラー時にAuthenticationErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_get.return_value = mock_response

        with pytest.raises(AuthenticationError) as excinfo:
            self.client.list_files()
        assert '認証に失敗' in str(excinfo.value)

    @patch('requests.get')
    def test_list_files_not_found(self, mock_get):
        """404エラー時にListOperationErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_get.return_value = mock_response

        with pytest.raises(ListOperationError) as excinfo:
            self.client.list_files('/nonexistent')
        assert 'フォルダが見つかりません' in str(excinfo.value)

    @patch('requests.get')
    def test_list_files_generic_error(self, mock_get):
        """その他のHTTPエラー時にListOperationErrorが発生すること"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_get.return_value = mock_response

        with pytest.raises(ListOperationError) as excinfo:
            self.client.list_files()
        assert '取得に失敗' in str(excinfo.value)