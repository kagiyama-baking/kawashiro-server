"""Tests for JMA weather client."""

from datetime import time
from unittest.mock import Mock, patch

import pytest
import requests

from weather.exceptions import (
    JMAAreaNotFoundError,
    JMANetworkError,
    JMAParseError,
    JMATimeoutError,
)
from weather.jma_client import JMAWeatherClient


class TestJMAWeatherClient:
    """Tests for JMAWeatherClient."""

    @pytest.fixture
    def sample_jma_response(self):
        """気象庁APIのサンプルレスポンス"""
        return [
            {
                "publishingOffice": "気象庁",
                "reportDatetime": "2025-12-23T17:00:00+09:00",
                "timeSeries": [
                    {
                        "timeDefines": [
                            "2025-12-23T17:00:00+09:00",
                            "2025-12-24T00:00:00+09:00",
                            "2025-12-25T00:00:00+09:00",
                        ],
                        "areas": [
                            {
                                "area": {"name": "東京地方", "code": "130010"},
                                "weatherCodes": ["111", "302", "202"],
                                "weathers": [
                                    "晴れ　夜　くもり",
                                    "雨　朝晩　くもり",
                                    "くもり　一時　雨",
                                ],
                            },
                            {
                                "area": {"name": "伊豆諸島北部", "code": "130020"},
                                "weatherCodes": ["111", "300", "313"],
                                "weathers": [
                                    "晴れ　夜　くもり",
                                    "雨",
                                    "雨　後　くもり",
                                ],
                            },
                        ],
                    },
                    {
                        "timeDefines": [
                            "2025-12-23T18:00:00+09:00",
                            "2025-12-24T00:00:00+09:00",
                            "2025-12-24T06:00:00+09:00",
                            "2025-12-24T12:00:00+09:00",
                            "2025-12-24T18:00:00+09:00",
                        ],
                        "areas": [
                            {
                                "area": {"name": "東京地方", "code": "130010"},
                                "pops": ["10", "30", "80", "80", "70"],
                            },
                            {
                                "area": {"name": "伊豆諸島北部", "code": "130020"},
                                "pops": ["10", "20", "80", "80", "80"],
                            },
                        ],
                    },
                    {
                        "timeDefines": [
                            "2025-12-24T00:00:00+09:00",
                            "2025-12-24T09:00:00+09:00",
                        ],
                        "areas": [
                            {
                                "area": {"name": "東京", "code": "44132"},
                                "temps": ["4", "7"],
                            },
                        ],
                    },
                ],
            },
            {
                "publishingOffice": "気象庁",
                "reportDatetime": "2025-12-23T17:00:00+09:00",
                "timeSeries": [
                    {
                        "timeDefines": [
                            "2025-12-24T00:00:00+09:00",
                            "2025-12-25T00:00:00+09:00",
                            "2025-12-26T00:00:00+09:00",
                        ],
                        "areas": [
                            {
                                "area": {"name": "東京都", "code": "130000"},
                                "weatherCodes": ["302", "202", "101"],
                                "pops": ["", "60", "20"],
                            },
                        ],
                    },
                    {
                        "timeDefines": [
                            "2025-12-24T00:00:00+09:00",
                            "2025-12-25T00:00:00+09:00",
                            "2025-12-26T00:00:00+09:00",
                        ],
                        "areas": [
                            {
                                "area": {"name": "東京", "code": "44132"},
                                "tempsMin": ["", "7", "5"],
                                "tempsMax": ["", "12", "10"],
                            },
                        ],
                    },
                ],
            },
        ]

    def test_get_prefecture_code_from_area_code(self):
        """予報区コードから都道府県コードを導出できる"""
        client = JMAWeatherClient()

        assert client.get_prefecture_code("130010") == "130000"
        assert client.get_prefecture_code("130020") == "130000"
        assert client.get_prefecture_code("270000") == "270000"
        assert client.get_prefecture_code("140010") == "140000"

    @patch("weather.jma_client.requests.get")
    def test_fetch_forecast_success(self, mock_get, sample_jma_response):
        """正常にAPIからデータを取得できる"""
        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.fetch_forecast("130000")

        assert result == sample_jma_response
        mock_get.assert_called_once_with(
            "https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json",
            timeout=10,
        )

    @patch("weather.jma_client.requests.get")
    def test_fetch_forecast_network_error(self, mock_get):
        """ネットワークエラー時にJMANetworkErrorを発生させる"""
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        client = JMAWeatherClient()

        with pytest.raises(JMANetworkError):
            client.fetch_forecast("130000")

    @patch("weather.jma_client.requests.get")
    def test_fetch_forecast_timeout_error(self, mock_get):
        """タイムアウト時にJMATimeoutErrorを発生させる"""
        mock_get.side_effect = requests.Timeout("Request timed out")

        client = JMAWeatherClient()

        with pytest.raises(JMATimeoutError):
            client.fetch_forecast("130000")

    @patch("weather.jma_client.requests.get")
    def test_fetch_forecast_invalid_json(self, mock_get):
        """不正なJSONの場合にJMAParseErrorを発生させる"""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()

        with pytest.raises(JMAParseError):
            client.fetch_forecast("130000")

    @patch("weather.jma_client.requests.get")
    def test_fetch_forecast_http_404_error(self, mock_get):
        """存在しない都道府県コードの場合（HTTP 404）にJMAAreaNotFoundErrorを発生させる"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "404 Client Error: Not Found"
        )
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        client = JMAWeatherClient()

        with pytest.raises(JMAAreaNotFoundError):
            client.fetch_forecast("999900")

    @patch("weather.jma_client.datetime")
    @patch("weather.jma_client.requests.get")
    def test_get_weather_today_tokyo(
        self, mock_get, mock_datetime, sample_jma_response
    ):
        """東京地方（130010）の今日の天気を取得できる"""
        # 通常時間帯（10時）を模擬
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=0)

        # area_nameは「都道府県名 地域名」の形式
        assert result["area_name"] == "東京都 東京地方"
        assert result["area_code"] == "130010"
        assert result["weather"] == "晴れ　夜　くもり"
        assert result["weather_code"] == "111"
        # 都道府県コードでAPIが呼ばれることを確認
        mock_get.assert_called_once_with(
            "https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json",
            timeout=10,
        )

    @patch("weather.jma_client.datetime")
    @patch("weather.jma_client.requests.get")
    def test_get_weather_today_izu(self, mock_get, mock_datetime, sample_jma_response):
        """伊豆諸島北部（130020）の今日の天気を取得できる"""
        # 通常時間帯（10時）を模擬
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130020", day=0)

        # area_nameは「都道府県名 地域名」の形式
        assert result["area_name"] == "東京都 伊豆諸島北部"
        assert result["area_code"] == "130020"
        assert result["weather"] == "晴れ　夜　くもり"
        assert result["weather_code"] == "111"

    @patch("weather.jma_client.datetime")
    @patch("weather.jma_client.requests.get")
    def test_get_weather_tomorrow(self, mock_get, mock_datetime, sample_jma_response):
        """明日の天気を取得できる"""
        # 通常時間帯（10時）を模擬
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=1)

        # area_nameは「都道府県名 地域名」の形式
        assert result["area_name"] == "東京都 東京地方"
        assert result["weather"] == "雨　朝晩　くもり"
        assert result["weather_code"] == "302"
        # 明日の気温
        assert result["temp_min"] == 4
        assert result["temp_max"] == 7

    @patch("weather.jma_client.datetime")
    @patch("weather.jma_client.requests.get")
    def test_get_weather_day_after_tomorrow(
        self, mock_get, mock_datetime, sample_jma_response
    ):
        """明後日の天気を取得できる"""
        # 通常時間帯（10時）を模擬
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=2)

        # area_nameは「都道府県名 地域名」の形式
        assert result["area_name"] == "東京都 東京地方"
        assert result["weather"] == "くもり　一時　雨"
        assert result["weather_code"] == "202"
        # 明後日の気温と降水確率は週間予報から取得
        # 週間予報のtimeDefines: [12/24, 12/25, 12/26] で day=2 は 12/25 (インデックス1)
        assert result["temp_min"] == 7
        assert result["temp_max"] == 12
        # 週間予報の降水確率を全時間帯に設定
        assert result["pop_00_06"] == 60
        assert result["pop_06_12"] == 60
        assert result["pop_12_18"] == 60
        assert result["pop_18_24"] == 60

    @patch("weather.jma_client.datetime")
    @patch("weather.jma_client.requests.get")
    def test_get_weather_with_pop_today(
        self, mock_get, mock_datetime, sample_jma_response
    ):
        """今日の降水確率を取得できる（18-24時のみ）"""
        # 通常時間帯（10時）を模擬
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=0)

        # 今日の場合、18時以降のみ取得可能
        assert result["pop_18_24"] == 10

    @patch("weather.jma_client.datetime")
    @patch("weather.jma_client.requests.get")
    def test_get_weather_with_pop_tomorrow(
        self, mock_get, mock_datetime, sample_jma_response
    ):
        """明日の降水確率を取得できる"""
        # 通常時間帯（10時）を模擬
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=1)

        # 明日は4つの時間帯の降水確率がある
        assert result["pop_00_06"] == 30
        assert result["pop_06_12"] == 80
        assert result["pop_12_18"] == 80
        assert result["pop_18_24"] == 70

    @patch("weather.jma_client.datetime")
    @patch("weather.jma_client.requests.get")
    def test_get_weather_area_not_found(
        self, mock_get, mock_datetime, sample_jma_response
    ):
        """存在しない予報区コードの場合はエラー"""
        # 通常時間帯（10時）を模擬
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()

        with pytest.raises(JMAAreaNotFoundError):
            client.get_weather("139999", day=0)

    def test_is_late_night_returns_true_during_0_to_5(self):
        """深夜帯（0時〜5時）の判定が正しく動作する"""
        client = JMAWeatherClient()

        # 深夜帯（0時〜5時）
        assert client._is_late_night(time(0, 0)) is True
        assert client._is_late_night(time(2, 30)) is True
        assert client._is_late_night(time(4, 59)) is True

        # 深夜帯外（5時以降）
        assert client._is_late_night(time(5, 0)) is False
        assert client._is_late_night(time(12, 0)) is False
        assert client._is_late_night(time(23, 59)) is False

    @patch("weather.jma_client.requests.get")
    @patch("weather.jma_client.datetime")
    def test_get_weather_today_during_late_night_uses_tomorrow_data(
        self, mock_datetime, mock_get, sample_jma_response
    ):
        """深夜帯にday=0を指定すると、timeDefines[1]のデータを「今日」として返す"""
        # 深夜3時を模擬
        mock_now = Mock()
        mock_now.time.return_value = time(3, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=0)

        # 深夜帯ではtimeDefines[1]（元の明日のデータ）が「今日」として返される
        assert result["date"] == "2025-12-24"  # 12/23ではなく12/24
        assert result["weather"] == "雨　朝晩　くもり"  # 元の明日の天気
        assert result["weather_code"] == "302"

    @patch("weather.jma_client.requests.get")
    @patch("weather.jma_client.datetime")
    def test_get_weather_today_during_late_night_gets_pop_from_tomorrow(
        self, mock_datetime, mock_get, sample_jma_response
    ):
        """深夜帯にday=0を指定すると、降水確率も翌日のデータを取得する"""
        mock_now = Mock()
        mock_now.time.return_value = time(3, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=0)

        # 深夜帯では元の明日の降水確率が返される
        assert result["pop_00_06"] == 30
        assert result["pop_06_12"] == 80
        assert result["pop_12_18"] == 80
        assert result["pop_18_24"] == 70

    @patch("weather.jma_client.requests.get")
    @patch("weather.jma_client.datetime")
    def test_get_weather_today_during_late_night_gets_temp_from_weekly(
        self, mock_datetime, mock_get, sample_jma_response
    ):
        """深夜帯にday=0を指定すると、気温は週間予報から取得する"""
        mock_now = Mock()
        mock_now.time.return_value = time(3, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=0)

        # 深夜帯では週間予報から気温を取得（インデックス0=明日のデータ）
        # 週間予報 tempsMin: ["", "7", "5"], tempsMax: ["", "12", "10"]
        # インデックス0（明日）は""なので、短期予報のtempsを使用
        assert result["temp_min"] == 4
        assert result["temp_max"] == 7

    @patch("weather.jma_client.requests.get")
    @patch("weather.jma_client.datetime")
    def test_get_weather_tomorrow_during_late_night(
        self, mock_datetime, mock_get, sample_jma_response
    ):
        """深夜帯にday=1を指定すると、timeDefines[2]のデータを「明日」として返す"""
        mock_now = Mock()
        mock_now.time.return_value = time(3, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=1)

        # 深夜帯ではtimeDefines[2]（元の明後日のデータ）が「明日」として返される
        assert result["date"] == "2025-12-25"
        assert result["weather"] == "くもり　一時　雨"
        assert result["weather_code"] == "202"
        # 週間予報から気温と降水確率を取得
        assert result["temp_min"] == 7
        assert result["temp_max"] == 12
        # 週間予報の降水確率を全時間帯に設定
        assert result["pop_00_06"] == 60
        assert result["pop_06_12"] == 60
        assert result["pop_12_18"] == 60
        assert result["pop_18_24"] == 60

    @patch("weather.jma_client.requests.get")
    @patch("weather.jma_client.datetime")
    def test_get_weather_normal_hours_uses_original_data(
        self, mock_datetime, mock_get, sample_jma_response
    ):
        """通常時間帯（5時以降）ではインデックス調整を行わない"""
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=0)

        # 通常時間帯ではtimeDefines[0]のデータが返される
        assert result["date"] == "2025-12-23"
        assert result["weather"] == "晴れ　夜　くもり"
        assert result["weather_code"] == "111"

    @patch("weather.jma_client.requests.get")
    @patch("weather.jma_client.datetime")
    def test_get_weather_day_after_tomorrow_during_late_night(
        self, mock_datetime, mock_get, sample_jma_response
    ):
        """深夜帯にday=2を指定すると、週間予報から明後日のデータを取得する"""
        mock_now = Mock()
        mock_now.time.return_value = time(3, 0)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.json.return_value = sample_jma_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = JMAWeatherClient()
        result = client.get_weather("130010", day=2)

        # 深夜帯では短期予報のインデックスは最大2までに制限
        # 週間予報からデータを取得（インデックス2=明後日）
        # 週間予報 timeDefines: [12/24, 12/25, 12/26]
        # day=2 で深夜帯なので、週間予報のインデックス2（12/26）を使用
        assert result["date"] == "2025-12-25"  # 短期予報の最後の日付
        assert result["weather"] == "くもり　一時　雨"  # 短期予報の最後のデータ
        assert result["weather_code"] == "202"
        # 気温と降水確率は週間予報から取得（インデックス2）
        assert result["temp_min"] == 5
        assert result["temp_max"] == 10
        # 週間予報の降水確率（インデックス2の20%）
        assert result["pop_00_06"] == 20
        assert result["pop_06_12"] == 20
        assert result["pop_12_18"] == 20
        assert result["pop_18_24"] == 20
