"""Microsoft Graph APIクライアント"""
import os
from msal import ConfidentialClientApplication
import requests
from django.conf import settings
from .exceptions import (
    ConfigurationError,
    AuthenticationError,
    UploadError,
    FolderOperationError,
    ListOperationError,
    NetworkError
)


class MSGraphClient:
    """Microsoft Graph APIにアクセスするためのクライアントクラス"""

    def __init__(self):
        """クライアントを初期化"""
        # 環境変数のチェック
        self.tenant_id = settings.AZURE_TENANT_ID
        self.client_id = settings.AZURE_CLIENT_ID
        self.thumbprint = settings.AZURE_CERT_THUMBPRINT
        self.key_file = settings.AZURE_CERT_KEY_FILE
        self.target_user = settings.TARGET_USER

        # 必須の環境変数が設定されているか確認
        missing_vars = []
        if not self.tenant_id:
            missing_vars.append('AZURE_TENANT_ID')
        if not self.client_id:
            missing_vars.append('AZURE_CLIENT_ID')
        if not self.thumbprint:
            missing_vars.append('AZURE_CERT_THUMBPRINT')
        if not self.key_file:
            missing_vars.append('AZURE_CERT_KEY_FILE')
        if not self.target_user:
            missing_vars.append('TARGET_USER')

        if missing_vars:
            raise ConfigurationError(
                f"以下の環境変数が設定されていません: {', '.join(missing_vars)}\n"
                ".envファイルを作成し、必要な環境変数を設定してください。"
            )

        # 秘密鍵ファイルの存在確認
        if not os.path.exists(self.key_file):
            raise ConfigurationError(
                f"秘密鍵ファイルが見つかりません: {self.key_file}\n"
                "AZURE_CERT_KEY_FILE環境変数で指定されたパスを確認してください。"
            )

        self.authority = f'https://login.microsoftonline.com/{self.tenant_id}'
        self.scopes = ['https://graph.microsoft.com/.default']
        self.graph_url = 'https://graph.microsoft.com/v1.0'

        self._access_token = None

    def acquire_token(self):
        """アクセストークンを取得"""
        # 秘密鍵ファイルを読み込み（バイナリモードで読み込んでからデコード）
        with open(self.key_file, 'rb') as fp:
            private_key = fp.read().decode('utf-8')

        # MSALアプリケーションを作成
        app = ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential={
                'private_key': private_key,
                'thumbprint': self.thumbprint
            },
        )

        # トークンを取得
        result = app.acquire_token_for_client(self.scopes)

        if 'access_token' not in result:
            error_msg = result.get('error_description', 'Unknown error')
            raise AuthenticationError(f'Failed to acquire token: {error_msg}')

        self._access_token = result['access_token']
        return self._access_token

    def get_headers(self):
        """認証ヘッダーを取得"""
        if not self._access_token:
            self.acquire_token()

        return {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/octet-stream',
            'Accept': 'application/json'
        }

    def upload_file_to_onedrive(self, file_content, file_name, folder_path='/'):
        """
        OneDriveにファイルをアップロード

        Args:
            file_content: ファイルのバイナリコンテンツ
            file_name: アップロードするファイル名
            folder_path: OneDrive上のフォルダパス（デフォルトはルート）

        Returns:
            dict: アップロード結果の情報
        """
        # URLを構築
        if folder_path.endswith('/'):
            path = f"{folder_path}{file_name}"
        else:
            path = f"{folder_path}/{file_name}"

        # 先頭のスラッシュを削除
        if path.startswith('/'):
            path = path[1:]

        # アップロードURL
        url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{path}:/content"

        # ヘッダーを取得
        headers = self.get_headers()

        try:
            # ファイルをアップロード
            response = requests.put(
                url,
                headers=headers,
                data=file_content,
                timeout=60
            )

            # トークンの有効期限切れの可能性があるため再取得を試みる
            if response.status_code == 401:
                try:
                    self.acquire_token()
                    headers = self.get_headers()

                    # 再試行
                    response = requests.put(
                        url,
                        headers=headers,
                        data=file_content,
                        timeout=60
                    )
                    response.raise_for_status()
                    return response.json()
                except Exception:
                    raise AuthenticationError('認証の更新に失敗しました')

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            raise NetworkError('ファイルアップロードがタイムアウトしました')
        except requests.exceptions.ConnectionError:
            raise NetworkError('OneDriveへの接続に失敗しました')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise UploadError('指定されたフォルダが見つかりません')
            elif e.response.status_code == 507:
                raise UploadError('OneDriveの容量が不足しています')
            elif e.response.status_code == 413:
                raise UploadError('ファイルサイズが大きすぎます')
            else:
                raise UploadError('ファイルのアップロードに失敗しました')
        except requests.exceptions.RequestException:
            raise UploadError('ファイルのアップロードに失敗しました')

    def create_folder(self, folder_name, parent_path='/'):
        """
        OneDriveにフォルダを作成

        Args:
            folder_name: 作成するフォルダ名
            parent_path: 親フォルダのパス

        Returns:
            dict: 作成されたフォルダの情報
        """
        # URLを構築
        if parent_path == '/' or parent_path == '':
            url = f"{self.graph_url}/users/{self.target_user}/drive/root/children"
        else:
            # 先頭のスラッシュを削除
            if parent_path.startswith('/'):
                parent_path = parent_path[1:]
            url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{parent_path}:/children"

        # リクエストボディ
        body = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename"
        }

        # ヘッダーを取得
        headers = self.get_headers()
        headers['Content-Type'] = 'application/json'

        try:
            # フォルダを作成
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=30
            )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            raise NetworkError('フォルダ作成がタイムアウトしました')
        except requests.exceptions.ConnectionError:
            raise NetworkError('OneDriveへの接続に失敗しました')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError('認証に失敗しました')
            elif e.response.status_code == 404:
                raise FolderOperationError('親フォルダが見つかりません')
            elif e.response.status_code == 409:
                raise FolderOperationError('同名のフォルダが既に存在します')
            else:
                raise FolderOperationError('フォルダの作成に失敗しました')
        except requests.exceptions.RequestException:
            raise FolderOperationError('フォルダの作成に失敗しました')

    def list_files(self, folder_path='/'):
        """
        指定したフォルダ内のファイル一覧を取得

        Args:
            folder_path: フォルダパス

        Returns:
            list: ファイル情報のリスト
        """
        # URLを構築
        if folder_path == '/' or folder_path == '':
            url = f"{self.graph_url}/users/{self.target_user}/drive/root/children"
        else:
            # 先頭のスラッシュを削除
            if folder_path.startswith('/'):
                folder_path = folder_path[1:]
            url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{folder_path}:/children"

        # ヘッダーを取得
        headers = self.get_headers()
        headers['Content-Type'] = 'application/json'

        try:
            # ファイル一覧を取得
            response = requests.get(
                url,
                headers=headers,
                timeout=30
            )

            response.raise_for_status()
            result = response.json()
            return result.get('value', [])

        except requests.exceptions.Timeout:
            raise NetworkError('ファイル一覧取得がタイムアウトしました')
        except requests.exceptions.ConnectionError:
            raise NetworkError('OneDriveへの接続に失敗しました')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError('認証に失敗しました')
            elif e.response.status_code == 404:
                raise ListOperationError('指定されたフォルダが見つかりません')
            else:
                raise ListOperationError('ファイル一覧の取得に失敗しました')
        except requests.exceptions.RequestException:
            raise ListOperationError('ファイル一覧の取得に失敗しました')