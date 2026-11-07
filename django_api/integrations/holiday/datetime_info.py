"""本日の日時情報（日付・時刻・曜日）の組み立て（祝日は呼び出し側が HolidayClient で確かめる）."""

from datetime import datetime
from typing import Any

from django.utils import timezone

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


def get_datetime_info_without_holiday() -> dict[str, Any]:
    """現在のタイムゾーンでの本日の日時情報を、祝日名なしで返す.

    現在時刻は 1 回だけ読む。祝日は呼び出し側が `date` で確かめる（読み直すと、分や日の
    境目をまたいで値がずれる）。

    Returns:
        date（YYYY-MM-DD）/ time（HH:MM:SS）/ day_of_week（英語の曜日名）/
        day_of_week_ja（日本語の曜日名）の dict
    """
    now = datetime.now(timezone.get_current_timezone())
    day_of_week = now.strftime("%A")
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": day_of_week,
        "day_of_week_ja": DAY_OF_WEEK_JA.get(day_of_week, day_of_week),
    }
