"""Holiday client for holidays-jp API."""

import requests

from .exceptions import HolidayNetworkError, HolidayTimeoutError


class HolidayClient:
    """祝日APIクライアント.

    holidays-jp.github.io APIを使用して日本の祝日情報を取得する。
    """

    API_URL = "https://holidays-jp.github.io/api/v1/date.json"
    TIMEOUT = 10

    def __init__(self):
        """クライアントを初期化."""
        self._holidays_cache: dict[str, str] | None = None

    def fetch_holidays(self) -> dict[str, str]:
        """祝日データを取得.

        Returns:
            日付文字列（YYYY-MM-DD）をキー、祝日名を値とするdict

        Raises:
            HolidayNetworkError: ネットワーク接続エラー
            HolidayTimeoutError: リクエストタイムアウト
        """
        try:
            response = requests.get(self.API_URL, timeout=self.TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.Timeout as e:
            raise HolidayTimeoutError(
                f"祝日APIへのリクエストがタイムアウトしました: {e}"
            ) from e
        except requests.RequestException as e:
            raise HolidayNetworkError(f"祝日APIへの接続に失敗しました: {e}") from e

    def get_holiday_name(self, date_str: str) -> str | None:
        """指定日が祝日かどうかを判定し、祝日名を返す.

        Args:
            date_str: 日付文字列（YYYY-MM-DD形式）

        Returns:
            祝日の場合は祝日名、祝日でない場合はNone

        Raises:
            HolidayNetworkError: ネットワーク接続エラー
            HolidayTimeoutError: リクエストタイムアウト
        """
        if self._holidays_cache is None:
            self._holidays_cache = self.fetch_holidays()

        return self._holidays_cache.get(date_str)
