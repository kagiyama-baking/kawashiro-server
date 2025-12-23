"""Microsoft Graph API クライアント（Outlook Calendar用）"""

from datetime import date, datetime, timedelta

import requests
from msal import ConfidentialClientApplication

from onedrive.config import get_ms_graph_settings

from .exceptions import (
    AuthenticationError,
    CalendarError,
    NetworkError,
)


class OutlookGraphClient:
    """Microsoft Graph APIを使用してOutlook Calendarにアクセスするクライアント"""

    def __init__(self):
        """クライアントを初期化"""
        # OneDriveと同じ設定を共有
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

    def get_headers(self):
        """認証ヘッダーを取得"""
        if not self._access_token:
            self.acquire_token()

        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": 'outlook.timezone="Asia/Tokyo"',
        }

    def get_calendar_events(self, start_date: date, end_date: date) -> list[dict]:
        """
        指定した期間のカレンダーイベントを取得

        Args:
            start_date: 取得開始日
            end_date: 取得終了日

        Returns:
            list[dict]: カレンダーイベントのリスト
        """
        # 日付をISO形式に変換（終日の範囲を含めるため、終了日は翌日の0時まで）
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(
            end_date + timedelta(days=1), datetime.min.time()
        )

        start_iso = start_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        end_iso = end_datetime.strftime("%Y-%m-%dT%H:%M:%S")

        # calendarViewエンドポイントを使用（繰り返しイベントを展開）
        url = (
            f"{self.graph_url}/users/{self.target_user}/calendar/calendarView"
            f"?startDateTime={start_iso}"
            f"&endDateTime={end_iso}"
            f"&$select=id,subject,start,end,location,isAllDay,organizer,webLink,bodyPreview"
            f"&$orderby=start/dateTime"
        )

        headers = self.get_headers()

        try:
            response = self._session.get(url, headers=headers, timeout=30)

            # 401エラーの場合、トークンを再取得してリトライ
            if response.status_code == 401:
                try:
                    self.acquire_token()
                    headers = self.get_headers()
                    response = self._session.get(url, headers=headers, timeout=30)
                    response.raise_for_status()
                    return response.json().get("value", [])
                except Exception as e:
                    raise AuthenticationError("認証の更新に失敗しました") from e

            response.raise_for_status()
            return response.json().get("value", [])

        except requests.exceptions.Timeout as e:
            raise NetworkError("カレンダー取得がタイムアウトしました") from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError("Outlookへの接続に失敗しました") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("認証に失敗しました") from e
            else:
                raise CalendarError("カレンダーイベントの取得に失敗しました") from e
        except requests.exceptions.RequestException as e:
            raise CalendarError("カレンダーイベントの取得に失敗しました") from e
