"""Microsoft Graph API 基底クライアント"""

from abc import ABC, abstractmethod

import requests
from msal import ConfidentialClientApplication

from .config import get_ms_graph_settings
from .exceptions import AuthenticationError


class BaseMSGraphClient(ABC):
    """Microsoft Graph APIにアクセスするための基底クライアントクラス"""

    def __init__(self):
        """クライアントを初期化"""
        # データベースから設定を取得
        config = get_ms_graph_settings()

        self.tenant_id = config.tenant_id
        self.client_id = config.client_id
        self.thumbprint = config.cert_thumbprint
        self._private_key = config.private_key
        self.target_user = config.target_user

        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scopes = ["https://graph.microsoft.com/.default"]
        self.graph_url = "https://graph.microsoft.com/v1.0"

        self._access_token = None
        self._session = requests.Session()

    def acquire_token(self):
        """アクセストークンを取得"""
        app = ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential={
                "private_key": self._private_key,
                "thumbprint": self.thumbprint,
            },
        )

        result = app.acquire_token_for_client(self.scopes)

        if "access_token" not in result:
            error_msg = result.get("error_description", "Unknown error")
            raise AuthenticationError(f"Failed to acquire token: {error_msg}")

        self._access_token = result["access_token"]
        return self._access_token

    @abstractmethod
    def get_headers(self) -> dict:
        """認証ヘッダーを取得（サブクラスで実装）"""

    def _get_base_headers(self) -> dict:
        """基本の認証ヘッダーを取得"""
        if not self._access_token:
            self.acquire_token()

        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
