"""Microsoft Graph API クライアント（Outlook Calendar用）"""

from datetime import date, datetime, timedelta

import requests
from django.utils import timezone

from integrations.outlook.exceptions import CalendarError

from .base import BaseMSGraphClient
from .exceptions import AuthenticationError, NetworkError


class OutlookMSGraphClient(BaseMSGraphClient):
    """Microsoft Graph APIを使用してOutlook Calendarにアクセスするクライアント"""

    def get_headers(self) -> dict:
        """認証ヘッダーを取得"""
        headers = self._get_base_headers()
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = 'outlook.timezone="Asia/Tokyo"'
        return headers

    def get_calendar_events(self, start_date: date, end_date: date) -> list[dict]:
        """
        指定した期間のカレンダーイベントを取得

        日付は Django の現在のタイムゾーンでの暦日として扱い、start_date の 0 時から
        end_date の翌日 0 時まで（終日の予定も含めるため）の期間に重なる予定を返す。

        Args:
            start_date: 取得開始日
            end_date: 取得終了日（この日を含む）

        Returns:
            list[dict]: カレンダーイベントのリスト
        """
        # Graph はオフセットのない日時を UTC として解釈するため、オフセット付きで渡す
        start_datetime = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_datetime = timezone.make_aware(
            datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

        # calendarViewエンドポイントを使用（繰り返しイベントを展開）
        url = f"{self.graph_url}/users/{self.target_user}/calendar/calendarView"
        # オフセットの「+」は URL に生のまま書くと空白と解釈されるため、
        # クエリのエンコードは requests に任せる
        params = {
            "startDateTime": start_datetime.isoformat(),
            "endDateTime": end_datetime.isoformat(),
            "$select": "id,subject,start,end,location,isAllDay,organizer,webLink,bodyPreview",
            "$orderby": "start/dateTime",
        }

        headers = self.get_headers()

        try:
            response = self._session.get(
                url, params=params, headers=headers, timeout=30
            )

            # 401エラーの場合、トークンを再取得してリトライ
            if response.status_code == 401:
                try:
                    self.acquire_token()
                    headers = self.get_headers()
                    response = self._session.get(
                        url, params=params, headers=headers, timeout=30
                    )
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
