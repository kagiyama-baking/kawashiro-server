"""get_datetime_info（本日の日時情報の組み立て）のテスト."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from integrations.holiday import (
    HolidayNetworkError,
    HolidayTimeoutError,
    get_datetime_info,
)

# 時刻の取得元と、クライアントを渡さないときに作られるクラス（patch 対象）
DATETIME_TARGET = "integrations.holiday.datetime_info.datetime"
CLIENT_CLASS_TARGET = "integrations.holiday.datetime_info.HolidayClient"


def _holiday_client(holiday_name: str | None = None) -> MagicMock:
    """get_holiday_name が holiday_name を返す祝日クライアントの代役."""
    client = MagicMock()
    client.get_holiday_name.return_value = holiday_name
    return client


@pytest.fixture
def mock_datetime():
    """現在時刻を 2025-01-14（火）09:30:00 に固定する."""
    with patch(DATETIME_TARGET) as mocked:
        mocked.now.return_value = datetime(2025, 1, 14, 9, 30, 0)
        yield mocked


@pytest.mark.unit
class TestGetDatetimeInfo:
    """get_datetime_info のテスト."""

    def test_get_datetime_info_on_weekday_returns_info_without_holiday_name(
        self, mock_datetime
    ):
        """平日は日付・時刻・曜日を返し、祝日名は None."""
        client = _holiday_client(None)

        result = get_datetime_info(client)

        assert result == {
            "date": "2025-01-14",
            "time": "09:30:00",
            "day_of_week": "Tuesday",
            "day_of_week_ja": "火曜日",
            "holiday_name": None,
        }

    def test_get_datetime_info_on_holiday_returns_holiday_name(self, mock_datetime):
        """祝日は祝日名を返す."""
        mock_datetime.now.return_value = datetime(2025, 1, 1, 8, 0, 0)

        result = get_datetime_info(_holiday_client("元日"))

        assert result["date"] == "2025-01-01"
        assert result["day_of_week_ja"] == "水曜日"
        assert result["holiday_name"] == "元日"

    def test_get_datetime_info_without_client_creates_default_client(
        self, mock_datetime
    ):
        """クライアントを渡さなければ HolidayClient を新しく作って使う."""
        with patch(CLIENT_CLASS_TARGET) as mock_client_class:
            mock_client_class.return_value = _holiday_client("元日")

            result = get_datetime_info()

        mock_client_class.assert_called_once_with()
        assert result["holiday_name"] == "元日"

    def test_get_datetime_info_with_client_uses_given_client(self, mock_datetime):
        """渡したクライアントで本日の日付を問い合わせ、新しくは作らない."""
        client = _holiday_client(None)

        with patch(CLIENT_CLASS_TARGET) as mock_client_class:
            get_datetime_info(client)

        mock_client_class.assert_not_called()
        client.get_holiday_name.assert_called_once_with("2025-01-14")

    @pytest.mark.parametrize("error_class", [HolidayTimeoutError, HolidayNetworkError])
    def test_get_datetime_info_with_holiday_api_error_raises_same_error(
        self, mock_datetime, error_class
    ):
        """祝日 API の例外は握りつぶさずそのまま送出する（HTTP への変換は呼び出し側）."""
        error = error_class("祝日APIの失敗")
        client = MagicMock()
        client.get_holiday_name.side_effect = error

        with pytest.raises(error_class) as exc_info:
            get_datetime_info(client)

        assert exc_info.value is error

    def test_get_datetime_info_with_active_timezone_gets_now_in_that_timezone(
        self, mock_datetime
    ):
        """現在時刻は有効なタイムゾーン（timezone.get_current_timezone()）で取る."""
        tz = ZoneInfo("America/New_York")

        with timezone.override(tz):
            get_datetime_info(_holiday_client(None))

        mock_datetime.now.assert_called_once_with(tz)
