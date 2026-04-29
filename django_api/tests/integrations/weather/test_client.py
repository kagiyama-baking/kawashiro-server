"""Tests for weather client (tsukumijima.net API)."""

from unittest.mock import Mock, patch

import pytest
import requests

from integrations.weather.client import WeatherClient
from integrations.weather.exceptions import (
    WeatherAreaNotFoundError,
    WeatherNetworkError,
    WeatherParseError,
    WeatherTimeoutError,
)


class TestWeatherClient:
    """Tests for WeatherClient."""

    @pytest.fixture
    def sample_tsukumijima_response(self):
        """tsukumijima天気予報APIのサンプルレスポンス"""
        return {
            "publicTime": "2025-12-24T05:00:00+09:00",
            "publicTimeFormatted": "2025/12/24 05:00:00",
            "publishingOffice": "気象庁",
            "title": "東京都 東京 の天気",
            "link": "https://www.jma.go.jp/bosai/forecast/#area_type=offices&area_code=130000",
            "description": {
                "publicTime": "2025-12-24T04:40:00+09:00",
                "publicTimeFormatted": "2025/12/24 04:40:00",
                "headlineText": "",
                "bodyText": "関東甲信地方は、高気圧に覆われています。",
                "text": "関東甲信地方は、高気圧に覆われています。",
            },
            "forecasts": [
                {
                    "date": "2025-12-24",
                    "dateLabel": "今日",
                    "telop": "晴れ",
                    "detail": {
                        "weather": "晴れ　昼過ぎ　から　くもり",
                        "wind": "北の風　後　南の風",
                        "wave": None,
                    },
                    "temperature": {
                        "min": {"celsius": "2", "fahrenheit": "35.6"},
                        "max": {"celsius": "12", "fahrenheit": "53.6"},
                    },
                    "chanceOfRain": {
                        "T00_06": "10%",
                        "T06_12": "0%",
                        "T12_18": "20%",
                        "T18_24": "30%",
                    },
                    "image": {
                        "title": "晴れ",
                        "url": "https://www.jma.go.jp/bosai/forecast/img/101.svg",
                        "width": 80,
                        "height": 60,
                    },
                },
                {
                    "date": "2025-12-25",
                    "dateLabel": "明日",
                    "telop": "くもり時々雨",
                    "detail": {
                        "weather": "くもり　時々　雨",
                        "wind": "南の風　やや強く",
                        "wave": None,
                    },
                    "temperature": {
                        "min": {"celsius": "8", "fahrenheit": "46.4"},
                        "max": {"celsius": "15", "fahrenheit": "59.0"},
                    },
                    "chanceOfRain": {
                        "T00_06": "20%",
                        "T06_12": "40%",
                        "T12_18": "60%",
                        "T18_24": "50%",
                    },
                    "image": {
                        "title": "くもり時々雨",
                        "url": "https://www.jma.go.jp/bosai/forecast/img/202.svg",
                        "width": 80,
                        "height": 60,
                    },
                },
                {
                    "date": "2025-12-26",
                    "dateLabel": "明後日",
                    "telop": "晴のち曇",
                    "detail": {"weather": None, "wind": None, "wave": None},
                    "temperature": {
                        "min": {"celsius": "5", "fahrenheit": "41.0"},
                        "max": {"celsius": "10", "fahrenheit": "50.0"},
                    },
                    "chanceOfRain": {
                        "T00_06": "10%",
                        "T06_12": "10%",
                        "T12_18": "20%",
                        "T18_24": "20%",
                    },
                    "image": {
                        "title": "晴のち曇",
                        "url": "https://www.jma.go.jp/bosai/forecast/img/110.svg",
                        "width": 80,
                        "height": 60,
                    },
                },
            ],
            "location": {
                "area": "関東",
                "prefecture": "東京都",
                "district": "東京地方",
                "city": "東京",
            },
            "copyright": {
                "title": "(C) 天気予報 API（livedoor 天気互換）",
                "link": "https://weather.tsukumijima.net/",
                "image": {},
                "provider": [],
            },
        }

    # ============================================================
    # fetch_forecast テスト
    # ============================================================

    @patch("integrations.weather.client.requests.get")
    def test_fetch_forecast_success(self, mock_get, sample_tsukumijima_response):
        """正常にAPIからデータを取得できる"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        result = client.fetch_forecast("130010")

        assert result == sample_tsukumijima_response
        mock_get.assert_called_once_with(
            "https://weather.tsukumijima.net/api/forecast/city/130010",
            timeout=10,
        )

    @pytest.mark.parametrize(
        "side_effect_factory, expected_exc",
        [
            pytest.param(
                lambda: requests.ConnectionError("Connection failed"),
                WeatherNetworkError,
                id="connection_error",
            ),
            pytest.param(
                lambda: requests.Timeout("Request timed out"),
                WeatherTimeoutError,
                id="timeout",
            ),
        ],
    )
    @patch("integrations.weather.client.requests.get")
    def test_fetch_forecast_network_errors(
        self, mock_get, side_effect_factory, expected_exc
    ):
        """ネットワーク系エラー時に対応する例外を発生させる"""
        mock_get.side_effect = side_effect_factory()

        client = WeatherClient()
        with pytest.raises(expected_exc):
            client.fetch_forecast("130010")

    @patch("integrations.weather.client.requests.get")
    def test_fetch_forecast_invalid_json(self, mock_get):
        """不正なJSONの場合にWeatherParseErrorを発生させる"""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        with pytest.raises(WeatherParseError):
            client.fetch_forecast("130010")

    @pytest.mark.parametrize(
        "status_code, expected_exc",
        [
            (404, WeatherAreaNotFoundError),
            (500, WeatherNetworkError),
        ],
        ids=["404_area_not_found", "500_server_error"],
    )
    @patch("integrations.weather.client.requests.get")
    def test_fetch_forecast_http_errors(self, mock_get, status_code, expected_exc):
        """HTTPエラー時に対応する例外を発生させる"""
        mock_response = Mock()
        mock_response.status_code = status_code
        http_error = requests.HTTPError(f"{status_code} HTTP Error")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response

        client = WeatherClient()
        with pytest.raises(expected_exc):
            client.fetch_forecast("130010")

    # ============================================================
    # get_weather テスト
    # ============================================================

    @pytest.mark.parametrize(
        "day, expected",
        [
            pytest.param(
                0,
                {
                    "date": "2025-12-24",
                    "weather": "晴れ　昼過ぎ　から　くもり",
                    "weather_code": "101",
                    "temp_min": 2,
                    "temp_max": 12,
                    "pop": (10, 0, 20, 30),
                },
                id="today",
            ),
            pytest.param(
                1,
                {
                    "date": "2025-12-25",
                    "weather": "くもり　時々　雨",
                    "weather_code": "202",
                    "temp_min": 8,
                    "temp_max": 15,
                    "pop": (20, 40, 60, 50),
                },
                id="tomorrow",
            ),
            pytest.param(
                2,
                {
                    # detail.weather が null の場合、telop にフォールバック
                    "date": "2025-12-26",
                    "weather": "晴のち曇",
                    "weather_code": "110",
                    "temp_min": 5,
                    "temp_max": 10,
                    "pop": (10, 10, 20, 20),
                },
                id="day_after_tomorrow_with_weather_fallback",
            ),
        ],
    )
    @patch("integrations.weather.client.requests.get")
    def test_get_weather_per_day(
        self, mock_get, sample_tsukumijima_response, day, expected
    ):
        """各日の天気を全フィールド正しく取得できること"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        result = client.get_weather("130010", day=day)

        assert result["area_name"] == "東京都 東京地方"
        assert result["area_code"] == "130010"
        assert result["date"] == expected["date"]
        assert result["weather"] == expected["weather"]
        assert result["weather_code"] == expected["weather_code"]
        assert result["temp_min"] == expected["temp_min"]
        assert result["temp_max"] == expected["temp_max"]
        assert result["pop_00_06"] == expected["pop"][0]
        assert result["pop_06_12"] == expected["pop"][1]
        assert result["pop_12_18"] == expected["pop"][2]
        assert result["pop_18_24"] == expected["pop"][3]

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_pop_unavailable(self, mock_get, sample_tsukumijima_response):
        """降水確率が「--%」の場合はNoneを返す"""
        sample_tsukumijima_response["forecasts"][0]["chanceOfRain"]["T00_06"] = "--%"
        sample_tsukumijima_response["forecasts"][0]["chanceOfRain"]["T06_12"] = "--%"

        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        result = client.get_weather("130010", day=0)

        assert result["pop_00_06"] is None
        assert result["pop_06_12"] is None
        assert result["pop_12_18"] == 20
        assert result["pop_18_24"] == 30

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_temp_null(self, mock_get, sample_tsukumijima_response):
        """気温がnullの場合はNoneを返す"""
        sample_tsukumijima_response["forecasts"][0]["temperature"]["min"]["celsius"] = (
            None
        )
        sample_tsukumijima_response["forecasts"][0]["temperature"]["max"]["celsius"] = (
            None
        )

        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        result = client.get_weather("130010", day=0)

        assert result["temp_min"] is None
        assert result["temp_max"] is None

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_area_not_found(self, mock_get):
        """存在しない地域コードの場合はWeatherAreaNotFoundError"""
        mock_response = Mock()
        mock_response.status_code = 404
        http_error = requests.HTTPError("404 Client Error: Not Found")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response

        client = WeatherClient()
        with pytest.raises(WeatherAreaNotFoundError):
            client.get_weather("999999", day=0)

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_invalid_day_index(self, mock_get, sample_tsukumijima_response):
        """dayが範囲外の場合にWeatherParseErrorを発生させる"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        with pytest.raises(WeatherParseError):
            client.get_weather("130010", day=3)

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_custom_timeout(self, mock_get, sample_tsukumijima_response):
        """カスタムタイムアウト値が使用される"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient(timeout=30)
        client.get_weather("130010", day=0)

        mock_get.assert_called_once_with(
            "https://weather.tsukumijima.net/api/forecast/city/130010",
            timeout=30,
        )

    # ============================================================
    # パース用ヘルパーメソッドのテスト
    # ============================================================

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("30%", 30),
            ("0%", 0),
            ("100%", 100),
            ("--%", None),
            ("", None),
            (None, None),
        ],
    )
    def test_parse_pop(self, value, expected):
        """降水確率文字列のパース"""
        client = WeatherClient()
        assert client._parse_pop(value) == expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("19", 19),
            ("0", 0),
            ("-3", -3),
            (None, None),
            ("", None),
        ],
    )
    def test_parse_temp(self, value, expected):
        """気温文字列のパース"""
        client = WeatherClient()
        assert client._parse_temp(value) == expected

    @pytest.mark.parametrize(
        "url, expected",
        [
            ("https://www.jma.go.jp/bosai/forecast/img/101.svg", "101"),
            ("https://www.jma.go.jp/bosai/forecast/img/202.svg", "202"),
            ("https://example.com/invalid", ""),
            ("", ""),
            (None, ""),
        ],
    )
    def test_extract_weather_code(self, url, expected):
        """image URLからweather codeを抽出"""
        client = WeatherClient()
        assert client._extract_weather_code(url) == expected
