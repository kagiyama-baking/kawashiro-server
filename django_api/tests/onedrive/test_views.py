"""OneDriveアプリのビューテスト"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from rest_framework import status


@pytest.mark.api
class TestOneDriveUploadView:
    """OneDriveUploadViewのテストクラス"""

    @patch('onedrive.views.MSGraphClient')
    def test_upload_file_success(self, mock_client_class, authenticated_client, mock_file):
        """ファイルのアップロードが成功すること"""
        # モッククライアントのセットアップ
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.return_value = {
            'name': 'test_file.txt',
            'size': 17,
            'created_datetime': '2024-01-01T00:00:00Z',
            'web_url': 'https://example.sharepoint.com/test_file.txt'
        }

        payload = {
            'file': mock_file,
            'folder_path': '/test_folder',
            'file_name': 'custom_name.txt'
        }

        response = authenticated_client.post('/onedrive/upload/', payload, format='multipart')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['message'] == 'ファイルが正常にアップロードされました'
        assert response.data['file_info']['name'] == 'test_file.txt'

        # クライアントメソッドが正しく呼ばれたことを確認
        mock_client.upload_file_to_onedrive.assert_called_once()
        call_args = mock_client.upload_file_to_onedrive.call_args
        assert call_args.kwargs['file_name'] == 'custom_name.txt'
        assert call_args.kwargs['folder_path'] == '/test_folder'

    def test_upload_file_without_authentication_fails(self, api_client, mock_file):
        """認証なしでファイルアップロードが失敗すること"""
        payload = {
            'file': mock_file
        }

        response = api_client.post('/onedrive/upload/', payload, format='multipart')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_upload_without_file_fails(self, authenticated_client):
        """ファイルなしでアップロードが失敗すること"""
        payload = {
            'folder_path': '/test_folder'
        }

        response = authenticated_client.post('/onedrive/upload/', payload, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'file' in response.data

    @patch('onedrive.views.MSGraphClient')
    def test_upload_file_with_configuration_error(self, mock_client_class, authenticated_client, mock_file):
        """設定エラー時に適切なエラーレスポンスを返すこと"""
        from onedrive.exceptions import ConfigurationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = ConfigurationError("Missing configuration")

        payload = {
            'file': mock_file
        }

        response = authenticated_client.post('/onedrive/upload/', payload, format='multipart')

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert 'サービスの設定に問題があります' in response.data['error']

    @patch('onedrive.views.MSGraphClient')
    def test_upload_file_with_authentication_error(self, mock_client_class, authenticated_client, mock_file):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from onedrive.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = AuthenticationError("Token expired")

        payload = {
            'file': mock_file
        }

        response = authenticated_client.post('/onedrive/upload/', payload, format='multipart')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert 'OneDriveへの認証に失敗しました' in response.data['error']

    @patch('onedrive.views.MSGraphClient')
    def test_upload_file_with_upload_error(self, mock_client_class, authenticated_client, mock_file):
        """アップロードエラー時に適切なエラーレスポンスを返すこと"""
        from onedrive.exceptions import UploadError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = UploadError("File too large")

        payload = {
            'file': mock_file
        }

        response = authenticated_client.post('/onedrive/upload/', payload, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['error'] == 'File too large'

    @patch('onedrive.views.MSGraphClient')
    def test_upload_file_with_network_error(self, mock_client_class, authenticated_client, mock_file):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from onedrive.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.upload_file_to_onedrive.side_effect = NetworkError("Connection timeout")

        payload = {
            'file': mock_file
        }

        response = authenticated_client.post('/onedrive/upload/', payload, format='multipart')

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'OneDriveへの接続に失敗しました' in response.data['error']


@pytest.mark.api
class TestOneDriveFolderView:
    """OneDriveFolderViewのテストクラス"""

    @patch('onedrive.views.MSGraphClient')
    def test_create_folder_success(self, mock_client_class, authenticated_client):
        """フォルダの作成が成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.create_folder.return_value = {
            'name': 'New Folder',
            'folder': {},
            'created_datetime': '2024-01-01T00:00:00Z',
            'web_url': 'https://example.sharepoint.com/New%20Folder'
        }

        payload = {
            'folder_name': 'New Folder',
            'parent_path': '/documents'
        }

        response = authenticated_client.post('/onedrive/folder/', payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['message'] == 'フォルダが正常に作成されました'
        assert response.data['folder_info']['name'] == 'New Folder'

        # クライアントメソッドが正しく呼ばれたことを確認
        mock_client.create_folder.assert_called_once_with(
            folder_name='New Folder',
            parent_path='/documents'
        )

    def test_create_folder_without_authentication_fails(self, api_client):
        """認証なしでフォルダ作成が失敗すること"""
        payload = {
            'folder_name': 'New Folder'
        }

        response = api_client.post('/onedrive/folder/', payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_folder_without_name_fails(self, authenticated_client):
        """フォルダ名なしでフォルダ作成が失敗すること"""
        payload = {
            'parent_path': '/documents'
        }

        response = authenticated_client.post('/onedrive/folder/', payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'folder_name' in response.data

    @patch('onedrive.views.MSGraphClient')
    def test_create_folder_with_folder_operation_error(self, mock_client_class, authenticated_client):
        """フォルダ操作エラー時に適切なエラーレスポンスを返すこと"""
        from onedrive.exceptions import FolderOperationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.create_folder.side_effect = FolderOperationError("Folder already exists")

        payload = {
            'folder_name': 'Existing Folder'
        }

        response = authenticated_client.post('/onedrive/folder/', payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['error'] == 'Folder already exists'


@pytest.mark.api
class TestOneDriveListView:
    """OneDriveListViewのテストクラス"""

    @patch('onedrive.views.MSGraphClient')
    def test_list_files_success(self, mock_client_class, authenticated_client):
        """ファイル一覧の取得が成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.return_value = [
            {
                'name': 'file1.pdf',
                'size': 1024000,
                'created_datetime': '2024-01-01T00:00:00Z',
                'web_url': 'https://example.sharepoint.com/file1.pdf'
            },
            {
                'name': 'folder1',
                'folder': {},
                'created_datetime': '2024-01-01T00:00:00Z',
                'web_url': 'https://example.sharepoint.com/folder1'
            }
        ]

        response = authenticated_client.get('/onedrive/list/', {'folder_path': '/documents'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['folder_path'] == '/documents'
        assert response.data['count'] == 2
        assert len(response.data['files']) == 2
        assert response.data['files'][0]['name'] == 'file1.pdf'

        # クライアントメソッドが正しく呼ばれたことを確認
        mock_client.list_files.assert_called_once_with(folder_path='/documents')

    @patch('onedrive.views.MSGraphClient')
    def test_list_files_root_directory(self, mock_client_class, authenticated_client):
        """ルートディレクトリのファイル一覧が取得できること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.return_value = []

        response = authenticated_client.get('/onedrive/list/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['folder_path'] == '/'
        assert response.data['count'] == 0

        # デフォルトでルートディレクトリが指定されることを確認
        mock_client.list_files.assert_called_once_with(folder_path='/')

    def test_list_files_without_authentication_fails(self, api_client):
        """認証なしでファイル一覧取得が失敗すること"""
        response = api_client.get('/onedrive/list/')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch('onedrive.views.MSGraphClient')
    def test_list_files_with_list_operation_error(self, mock_client_class, authenticated_client):
        """一覧取得操作エラー時に適切なエラーレスポンスを返すこと"""
        from onedrive.exceptions import ListOperationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_files.side_effect = ListOperationError("Folder not found")

        response = authenticated_client.get('/onedrive/list/', {'folder_path': '/nonexistent'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['error'] == 'Folder not found'