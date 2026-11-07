"""本日の日時情報の組み立て（get_datetime_info_without_holiday）のテスト."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from integrations.holiday import get_datetime_info_without_holiday

# 時刻の取得元（patch 対象）
DATETIME_TARGET = "integrations.holiday.datetime_info.datetime"


@pytest.fixture
def mock_datetime():
    """現在時刻を 2025-01-14（火）09:30:00 に固定する."""
    with patch(DATETIME_TARGET) as mocked:
        mocked.now.return_value = datetime(2025, 1, 14, 9, 30, 0)
        yield mocked


@pytest.mark.unit
class TestGetDatetimeInfoWithoutHoliday:
    """get_datetime_info_without_holiday（祝日名を含まない日時情報）のテスト."""

    def test_get_datetime_info_without_holiday_returns_only_date_time_and_weekday(
        self, mock_datetime
    ):
        """日付・時刻・曜日だけを返す（祝日名は含めない）."""
        result = get_datetime_info_without_holiday()

        assert result == {
            "date": "2025-01-14",
            "time": "09:30:00",
            "day_of_week": "Tuesday",
            "day_of_week_ja": "火曜日",
        }

    def test_get_datetime_info_without_holiday_reads_now_once_in_active_timezone(
        self, mock_datetime
    ):
        """現在時刻は有効なタイムゾーンで 1 回だけ読む."""
        tz = ZoneInfo("America/New_York")

        with timezone.override(tz):
            get_datetime_info_without_holiday()

        mock_datetime.now.assert_called_once_with(tz)
