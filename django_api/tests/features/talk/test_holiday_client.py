"""Tests for holiday client."""

from unittest.mock import Mock, patch

import pytest
import requests

from features.talk.exceptions import HolidayNetworkError, HolidayTimeoutError
from features.talk.holiday_client import HolidayClient


class TestHolidayClient:
    """Tests for HolidayClient."""

    @pytest.fixture
    def sample_holidays_response(self):
        """holidays-jp APIのサンプルレスポンス"""
        return {
            "2025-01-01": "元日",
            "2025-01-13": "成人の日",
            "2025-02-11": "建国記念の日",
            "2025-02-23": "天皇誕生日",
            "2025-02-24": "天皇誕生日 振替休日",
            "2025-03-20": "春分の日",
            "2025-04-29": "昭和の日",
            "2025-05-03": "憲法記念日",
            "2025-05-04": "みどりの日",
            "2025-05-05": "こどもの日",
            "2025-05-06": "こどもの日 振替休日",
        }

    @patch("features.talk.holiday_client.requests.get")
    def test_fetch_holidays_success(self, mock_get, sample_holidays_response):
        """正常にAPIからデータを取得できる"""
        mock_response = Mock()
        mock_response.json.return_value = sample_holidays_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = HolidayClient()
        result = client.fetch_holidays()

        assert result == sample_holidays_response
        mock_get.assert_called_once_with(
            "https://holidays-jp.github.io/api/v1/date.json",
            timeout=10,
        )

    @patch("features.talk.holiday_client.requests.get")
    def test_fetch_holidays_network_error(self, mock_get):
        """ネットワークエラー時にHolidayNetworkErrorを発生させる"""
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        client = HolidayClient()

        with pytest.raises(HolidayNetworkError):
            client.fetch_holidays()

    @patch("features.talk.holiday_client.requests.get")
    def test_fetch_holidays_timeout_error(self, mock_get):
        """タイムアウト時にHolidayTimeoutErrorを発生させる"""
        mock_get.side_effect = requests.Timeout("Request timed out")

        client = HolidayClient()

        with pytest.raises(HolidayTimeoutError):
            client.fetch_holidays()

    @patch("features.talk.holiday_client.requests.get")
    def test_get_holiday_name_returns_name_on_holiday(
        self, mock_get, sample_holidays_response
    ):
        """祝日の場合は祝日名を返す"""
        mock_response = Mock()
        mock_response.json.return_value = sample_holidays_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = HolidayClient()
        result = client.get_holiday_name("2025-01-01")

        assert result == "元日"

    @patch("features.talk.holiday_client.requests.get")
    def test_get_holiday_name_returns_none_on_non_holiday(
        self, mock_get, sample_holidays_response
    ):
        """祝日でない場合はNoneを返す"""
        mock_response = Mock()
        mock_response.json.return_value = sample_holidays_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = HolidayClient()
        result = client.get_holiday_name("2025-01-02")

        assert result is None

    @patch("features.talk.holiday_client.requests.get")
    def test_get_holiday_name_with_substitute_holiday(
        self, mock_get, sample_holidays_response
    ):
        """振替休日の場合も祝日名を返す"""
        mock_response = Mock()
        mock_response.json.return_value = sample_holidays_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = HolidayClient()
        result = client.get_holiday_name("2025-02-24")

        assert result == "天皇誕生日 振替休日"

    @patch("features.talk.holiday_client.requests.get")
    def test_holidays_are_cached(self, mock_get, sample_holidays_response):
        """祝日データはキャッシュされる"""
        mock_response = Mock()
        mock_response.json.return_value = sample_holidays_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = HolidayClient()

        # 2回呼び出し
        client.get_holiday_name("2025-01-01")
        client.get_holiday_name("2025-01-02")

        # APIは1回だけ呼ばれる
        assert mock_get.call_count == 1
