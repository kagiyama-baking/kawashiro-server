"""Microsoft Graph API クライアント（OneDrive用）"""

import time
from urllib.parse import quote

import requests

from integrations.onedrive.exceptions import (
    DeleteError,
    DownloadError,
    FolderOperationError,
    ListOperationError,
    OneDriveFileNotFoundError,
    UploadError,
)

from .base import BaseMSGraphClient
from .exceptions import AuthenticationError, NetworkError

# アップロードセッションの定数
CHUNK_SIZE = 60 * 1024 * 1024  # 60MB (320KiBの倍数、Graph API最大値)
SIMPLE_UPLOAD_THRESHOLD = 4 * 1024 * 1024  # 4MB未満はシンプルアップロード


class OneDriveMSGraphClient(BaseMSGraphClient):
    """Microsoft Graph APIを使用してOneDriveにアクセスするクライアント"""

    def get_headers(self) -> dict:
        """認証ヘッダーを取得"""
        headers = self._get_base_headers()
        headers["Content-Type"] = "application/octet-stream"
        return headers

    def upload_file_to_onedrive(self, file_content, file_name, folder_path="/"):
        """
        OneDriveにファイルをアップロード
        ファイルサイズに応じて最適な方法を選択します。

        Args:
            file_content: ファイルのバイナリコンテンツ
            file_name: アップロードするファイル名
            folder_path: OneDrive上のフォルダパス（デフォルトはルート）

        Returns:
            dict: アップロード結果の情報
        """
        file_size = len(file_content)

        # 4MB未満はシンプルアップロード、それ以上はアップロードセッション
        if file_size < SIMPLE_UPLOAD_THRESHOLD:
            return self._simple_upload(file_content, file_name, folder_path)
        else:
            return self._upload_large_file(file_content, file_name, folder_path)

    def _simple_upload(self, file_content, file_name, folder_path="/"):
        """
        4MB未満のファイルをシンプルアップロード

        Args:
            file_content: ファイルのバイナリコンテンツ
            file_name: アップロードするファイル名
            folder_path: OneDrive上のフォルダパス

        Returns:
            dict: アップロード結果の情報
        """
        # URLを構築
        if folder_path.endswith("/"):
            path = f"{folder_path}{file_name}"
        else:
            path = f"{folder_path}/{file_name}"

        # 先頭のスラッシュを削除
        if path.startswith("/"):
            path = path[1:]

        # アップロードURL
        url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{path}:/content"

        # ヘッダーを取得
        headers = self.get_headers()

        try:
            # ファイルをアップロード（セッションを使用して接続を再利用）
            response = self._session.put(
                url, headers=headers, data=file_content, timeout=60
            )

            # トークンの有効期限切れの可能性があるため再取得を試みる
            if response.status_code == 401:
                try:
                    self.acquire_token()
                    headers = self.get_headers()

                    # 再試行
                    response = self._session.put(
                        url, headers=headers, data=file_content, timeout=60
                    )
                    response.raise_for_status()
                    return response.json()
                except Exception as e:
                    raise AuthenticationError("認証の更新に失敗しました") from e

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            raise NetworkError("ファイルアップロードがタイムアウトしました") from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError("OneDriveへの接続に失敗しました") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise UploadError("指定されたフォルダが見つかりません") from e
            elif e.response.status_code == 507:
                raise UploadError("OneDriveの容量が不足しています") from e
            elif e.response.status_code == 413:
                raise UploadError("ファイルサイズが大きすぎます") from e
            else:
                raise UploadError("ファイルのアップロードに失敗しました") from e
        except requests.exceptions.RequestException as e:
            raise UploadError("ファイルのアップロードに失敗しました") from e

    def _upload_large_file(self, file_content, file_name, folder_path="/"):
        """
        4MB以上のファイルをアップロードセッションを使用してアップロード

        Args:
            file_content: ファイルのバイナリコンテンツ
            file_name: アップロードするファイル名
            folder_path: OneDrive上のフォルダパス

        Returns:
            dict: アップロード結果の情報
        """
        # アップロードセッションを作成
        upload_url = self._create_upload_session(file_name, folder_path)

        # ファイルをチャンクに分割してアップロード
        file_size = len(file_content)
        offset = 0

        try:
            while offset < file_size:
                # チャンクサイズを計算
                chunk_size = min(CHUNK_SIZE, file_size - offset)
                chunk_data = file_content[offset : offset + chunk_size]

                # チャンクをアップロード
                result = self._upload_chunk(upload_url, chunk_data, offset, file_size)

                # アップロード完了を確認
                if result.get("id"):
                    # アップロード成功
                    return result

                offset += chunk_size

            raise UploadError("ファイルのアップロードが完了しませんでした")

        except requests.exceptions.Timeout as e:
            raise NetworkError("ファイルアップロードがタイムアウトしました") from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError("OneDriveへの接続に失敗しました") from e
        except requests.exceptions.RequestException as e:
            raise UploadError("ファイルのアップロードに失敗しました") from e

    def _create_upload_session(self, file_name, folder_path="/"):
        """
        アップロードセッションを作成

        Args:
            file_name: アップロードするファイル名
            folder_path: OneDrive上のフォルダパス

        Returns:
            str: アップロードURL
        """
        # URLを構築
        if folder_path.endswith("/"):
            path = f"{folder_path}{file_name}"
        else:
            path = f"{folder_path}/{file_name}"

        # 先頭のスラッシュを削除
        if path.startswith("/"):
            path = path[1:]

        # セッション作成URL
        url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{path}:/createUploadSession"

        # ヘッダーを取得
        headers = self.get_headers()
        headers["Content-Type"] = "application/json"

        # リクエストボディ
        body = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}

        try:
            response = self._session.post(url, headers=headers, json=body, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result["uploadUrl"]

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("認証に失敗しました") from e
            elif e.response.status_code == 404:
                raise UploadError("指定されたフォルダが見つかりません") from e
            else:
                raise UploadError("アップロードセッションの作成に失敗しました") from e
        except requests.exceptions.RequestException as e:
            raise UploadError("アップロードセッションの作成に失敗しました") from e
        except KeyError as e:
            raise UploadError(
                "アップロードセッションのURLが取得できませんでした"
            ) from e

    def _upload_chunk(self, upload_url, chunk_data, offset, total_size, max_retries=3):
        """
        ファイルチャンクをアップロード（リトライ機能付き）

        Args:
            upload_url: アップロードURL
            chunk_data: チャンクデータ
            offset: ファイル内のオフセット位置
            total_size: ファイルの総サイズ
            max_retries: 最大リトライ回数

        Returns:
            dict: アップロード結果
        """
        chunk_size = len(chunk_data)
        end = offset + chunk_size - 1

        headers = {
            "Content-Length": str(chunk_size),
            "Content-Range": f"bytes {offset}-{end}/{total_size}",
        }

        for attempt in range(max_retries):
            try:
                response = self._session.put(
                    upload_url,
                    headers=headers,
                    data=chunk_data,
                    timeout=300,  # 5分のタイムアウト
                )

                # 202 Acceptedは継続、200/201は完了
                if response.status_code in [200, 201]:
                    return response.json()
                elif response.status_code == 202:
                    # 継続中
                    return response.json()
                else:
                    response.raise_for_status()

            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ):
                if attempt < max_retries - 1:
                    # 指数バックオフでリトライ
                    wait_time = 2**attempt
                    time.sleep(wait_time)
                    continue
                else:
                    # ネットワークエラーは呼び出し元でNetworkErrorに変換
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    # 指数バックオフでリトライ
                    wait_time = 2**attempt
                    time.sleep(wait_time)
                    continue
                else:
                    raise UploadError(
                        f"チャンクのアップロードに失敗しました: {str(e)}"
                    ) from e

    def create_folder(self, folder_name, parent_path="/"):
        """
        OneDriveにフォルダを作成

        Args:
            folder_name: 作成するフォルダ名
            parent_path: 親フォルダのパス

        Returns:
            dict: 作成されたフォルダの情報
        """
        # URLを構築
        if parent_path == "/" or parent_path == "":
            url = f"{self.graph_url}/users/{self.target_user}/drive/root/children"
        else:
            # 先頭のスラッシュを削除
            if parent_path.startswith("/"):
                parent_path = parent_path[1:]
            url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{parent_path}:/children"

        # リクエストボディ
        body = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename",
        }

        # ヘッダーを取得
        headers = self.get_headers()
        headers["Content-Type"] = "application/json"

        try:
            # フォルダを作成（セッションを使用して接続を再利用）
            response = self._session.post(url, headers=headers, json=body, timeout=30)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            raise NetworkError("フォルダ作成がタイムアウトしました") from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError("OneDriveへの接続に失敗しました") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("認証に失敗しました") from e
            elif e.response.status_code == 404:
                raise FolderOperationError("親フォルダが見つかりません") from e
            elif e.response.status_code == 409:
                raise FolderOperationError("同名のフォルダが既に存在します") from e
            else:
                raise FolderOperationError("フォルダの作成に失敗しました") from e
        except requests.exceptions.RequestException as e:
            raise FolderOperationError("フォルダの作成に失敗しました") from e

    def list_files(self, folder_path="/"):
        """
        指定したフォルダ内のファイル一覧を取得

        Args:
            folder_path: フォルダパス

        Returns:
            list: ファイル情報のリスト
        """
        # URLを構築
        if folder_path == "/" or folder_path == "":
            url = f"{self.graph_url}/users/{self.target_user}/drive/root/children"
        else:
            # 先頭のスラッシュを削除
            if folder_path.startswith("/"):
                folder_path = folder_path[1:]
            url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{folder_path}:/children"

        # ヘッダーを取得
        headers = self.get_headers()
        headers["Content-Type"] = "application/json"

        try:
            # ファイル一覧を取得（セッションを使用して接続を再利用）
            response = self._session.get(url, headers=headers, timeout=30)

            response.raise_for_status()
            result = response.json()
            return result.get("value", [])

        except requests.exceptions.Timeout as e:
            raise NetworkError("ファイル一覧取得がタイムアウトしました") from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError("OneDriveへの接続に失敗しました") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("認証に失敗しました") from e
            elif e.response.status_code == 404:
                raise ListOperationError("指定されたフォルダが見つかりません") from e
            else:
                raise ListOperationError("ファイル一覧の取得に失敗しました") from e
        except requests.exceptions.RequestException as e:
            raise ListOperationError("ファイル一覧の取得に失敗しました") from e

    def delete_file(self, file_path, permanent_delete=False):
        """
        指定したファイルを削除

        Args:
            file_path: 削除するファイルのパス
            permanent_delete: Trueの場合、ごみ箱からも完全削除する

        Raises:
            DeleteError: ファイル削除に失敗した場合
            AuthenticationError: 認証に失敗した場合
            NetworkError: ネットワーク接続に失敗した場合
        """
        # 先頭のスラッシュを削除
        if file_path.startswith("/"):
            file_path = file_path[1:]

        # ヘッダーを取得
        headers = self.get_headers()
        headers["Content-Type"] = "application/json"

        try:
            # ファイルパスをURLエンコード
            encoded_path = quote(file_path, safe="/")

            if permanent_delete:
                # 完全削除の場合、まずアイテムIDを取得
                item_url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{encoded_path}"
                response = self._session.get(item_url, headers=headers, timeout=30)
                response.raise_for_status()
                item_data = response.json()
                item_id = item_data.get("id")

                if not item_id:
                    raise DeleteError("ファイルのIDを取得できませんでした")

                # permanentDeleteアクションを実行
                permanent_delete_url = f"{self.graph_url}/users/{self.target_user}/drive/items/{item_id}/permanentDelete"
                response = self._session.post(
                    permanent_delete_url, headers=headers, timeout=30
                )
                response.raise_for_status()
            else:
                # 通常の削除（ごみ箱に移動）
                url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{encoded_path}"
                response = self._session.delete(url, headers=headers, timeout=30)
                response.raise_for_status()

        except requests.exceptions.Timeout as e:
            raise NetworkError("ファイル削除がタイムアウトしました") from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError("OneDriveへの接続に失敗しました") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("認証に失敗しました") from e
            elif e.response.status_code == 404:
                raise DeleteError("指定されたファイルが見つかりません") from e
            else:
                raise DeleteError("ファイルの削除に失敗しました") from e
        except requests.exceptions.RequestException as e:
            raise DeleteError("ファイルの削除に失敗しました") from e

    def download_file(self, file_path):
        """
        指定したファイルをダウンロード

        Args:
            file_path: ダウンロードするファイルのパス

        Returns:
            tuple: (ファイル内容(bytes), ファイル名(str))

        Raises:
            DownloadError: ファイルダウンロードに失敗した場合
            OneDriveFileNotFoundError: ファイルが見つからない場合
            AuthenticationError: 認証に失敗した場合
            NetworkError: ネットワーク接続に失敗した場合
        """
        # 先頭のスラッシュを削除
        if file_path.startswith("/"):
            file_path = file_path[1:]

        # ヘッダーを取得
        headers = self.get_headers()

        try:
            # ファイルパスをURLエンコード
            encoded_path = quote(file_path, safe="/")

            # ファイルのメタデータを取得してファイル名を取得
            metadata_url = (
                f"{self.graph_url}/users/{self.target_user}/drive/root:/{encoded_path}"
            )
            metadata_response = self._session.get(
                metadata_url, headers=headers, timeout=30
            )
            metadata_response.raise_for_status()
            metadata = metadata_response.json()
            file_name = metadata.get("name", file_path.split("/")[-1])

            # ファイルの内容をダウンロード（セッションを使用して接続を再利用）
            download_url = f"{self.graph_url}/users/{self.target_user}/drive/root:/{encoded_path}:/content"
            response = self._session.get(
                download_url,
                headers=headers,
                timeout=300,  # 大きなファイルの場合は長めのタイムアウト
            )
            response.raise_for_status()

            return (response.content, file_name)

        except requests.exceptions.Timeout as e:
            raise NetworkError("ファイルダウンロードがタイムアウトしました") from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError("OneDriveへの接続に失敗しました") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("認証に失敗しました") from e
            elif e.response.status_code == 404:
                raise OneDriveFileNotFoundError(
                    "指定されたファイルが見つかりません"
                ) from e
            else:
                raise DownloadError("ファイルのダウンロードに失敗しました") from e
        except requests.exceptions.RequestException as e:
            raise DownloadError("ファイルのダウンロードに失敗しました") from e
