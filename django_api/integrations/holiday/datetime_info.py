"""本日の日時情報（日付・時刻・曜日・祝日名）の組み立て."""

from datetime import datetime
from typing import Any

from django.utils import timezone

from .client import HolidayClient

# 曜日の日本語マッピング
DAY_OF_WEEK_JA = {
    "Monday": "月曜日",
    "Tuesday": "火曜日",
    "Wednesday": "水曜日",
    "Thursday": "木曜日",
    "Friday": "金曜日",
    "Saturday": "土曜日",
    "Sunday": "日曜日",
}


def get_datetime_info(holiday_client: HolidayClient | None = None) -> dict[str, Any]:
    """現在のタイムゾーンでの本日の日時情報を返す.

    Args:
        holiday_client: 祝日の判定に使うクライアント。省略時は新しく作る。
            祝日データはクライアントのインスタンス内にキャッシュされるので、
            使い回したい場合は渡す

    Returns:
        date（YYYY-MM-DD）/ time（HH:MM:SS）/ day_of_week（英語の曜日名）/
        day_of_week_ja（日本語の曜日名）/ holiday_name（祝日でなければ None）の dict

    Raises:
        HolidayNetworkError: 祝日APIへのネットワーク接続エラー
        HolidayTimeoutError: 祝日APIへのリクエストタイムアウト
    """
    now = datetime.now(timezone.get_current_timezone())
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    day_of_week = now.strftime("%A")
    day_of_week_ja = DAY_OF_WEEK_JA.get(day_of_week, day_of_week)

    client = holiday_client if holiday_client is not None else HolidayClient()
    holiday_name = client.get_holiday_name(date_str)

    return {
        "date": date_str,
        "time": time_str,
        "day_of_week": day_of_week,
        "day_of_week_ja": day_of_week_ja,
        "holiday_name": holiday_name,
    }
