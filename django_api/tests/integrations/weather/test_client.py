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
                        "min": {
                            "celsius": "2",
                            "fahrenheit": "35.6",
                        },
                        "max": {
                            "celsius": "12",
                            "fahrenheit": "53.6",
                        },
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
                        "min": {
                            "celsius": "8",
                            "fahrenheit": "46.4",
                        },
                        "max": {
                            "celsius": "15",
                            "fahrenheit": "59.0",
                        },
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
                    "detail": {
                        "weather": None,
                        "wind": None,
                        "wave": None,
                    },
                    "temperature": {
                        "min": {
                            "celsius": "5",
                            "fahrenheit": "41.0",
                        },
                        "max": {
                            "celsius": "10",
                            "fahrenheit": "50.0",
                        },
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

    # fetch_forecast テスト

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

    @patch("integrations.weather.client.requests.get")
    def test_fetch_forecast_network_error(self, mock_get):
        """ネットワークエラー時にWeatherNetworkErrorを発生させる"""
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        client = WeatherClient()

        with pytest.raises(WeatherNetworkError):
            client.fetch_forecast("130010")

    @patch("integrations.weather.client.requests.get")
    def test_fetch_forecast_timeout_error(self, mock_get):
        """タイムアウト時にWeatherTimeoutErrorを発生させる"""
        mock_get.side_effect = requests.Timeout("Request timed out")

        client = WeatherClient()

        with pytest.raises(WeatherTimeoutError):
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

    @patch("integrations.weather.client.requests.get")
    def test_fetch_forecast_http_404_error(self, mock_get):
        """存在しない地域コードの場合（HTTP 404）にWeatherAreaNotFoundErrorを発生させる"""
        mock_response = Mock()
        mock_response.status_code = 404
        http_error = requests.HTTPError("404 Client Error: Not Found")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response

        client = WeatherClient()

        with pytest.raises(WeatherAreaNotFoundError):
            client.fetch_forecast("999999")

    @patch("integrations.weather.client.requests.get")
    def test_fetch_forecast_http_500_error(self, mock_get):
        """サーバーエラー（HTTP 500）の場合にWeatherNetworkErrorを発生させる"""
        mock_response = Mock()
        mock_response.status_code = 500
        http_error = requests.HTTPError("500 Server Error")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response

        client = WeatherClient()

        with pytest.raises(WeatherNetworkError):
            client.fetch_forecast("130010")

    # get_weather テスト

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_today(self, mock_get, sample_tsukumijima_response):
        """今日の天気を全フィールド正しく取得できる"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        result = client.get_weather("130010", day=0)

        assert result["area_name"] == "東京都 東京地方"
        assert result["area_code"] == "130010"
        assert result["date"] == "2025-12-24"
        assert result["weather"] == "晴れ　昼過ぎ　から　くもり"
        assert result["weather_code"] == "101"
        assert result["temp_min"] == 2
        assert result["temp_max"] == 12
        assert result["pop_00_06"] == 10
        assert result["pop_06_12"] == 0
        assert result["pop_12_18"] == 20
        assert result["pop_18_24"] == 30

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_tomorrow(self, mock_get, sample_tsukumijima_response):
        """明日の天気を取得できる"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        result = client.get_weather("130010", day=1)

        assert result["area_name"] == "東京都 東京地方"
        assert result["area_code"] == "130010"
        assert result["date"] == "2025-12-25"
        assert result["weather"] == "くもり　時々　雨"
        assert result["weather_code"] == "202"
        assert result["temp_min"] == 8
        assert result["temp_max"] == 15
        assert result["pop_00_06"] == 20
        assert result["pop_06_12"] == 40
        assert result["pop_12_18"] == 60
        assert result["pop_18_24"] == 50

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_day_after_tomorrow(
        self, mock_get, sample_tsukumijima_response
    ):
        """明後日の天気を取得できる"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        result = client.get_weather("130010", day=2)

        assert result["area_name"] == "東京都 東京地方"
        assert result["area_code"] == "130010"
        assert result["date"] == "2025-12-26"
        assert result["weather_code"] == "110"
        assert result["temp_min"] == 5
        assert result["temp_max"] == 10
        assert result["pop_00_06"] == 10
        assert result["pop_06_12"] == 10
        assert result["pop_12_18"] == 20
        assert result["pop_18_24"] == 20

    @patch("integrations.weather.client.requests.get")
    def test_get_weather_weather_fallback_to_telop(
        self, mock_get, sample_tsukumijima_response
    ):
        """detail.weatherがnullの場合、telopにフォールバックする"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()
        # 明後日のdetail.weatherはnull
        result = client.get_weather("130010", day=2)

        assert result["weather"] == "晴のち曇"

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
    def test_get_weather_code_extraction(self, mock_get, sample_tsukumijima_response):
        """image URLからweather_codeを正しく抽出する"""
        mock_response = Mock()
        mock_response.json.return_value = sample_tsukumijima_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = WeatherClient()

        # day=0: 101.svg → "101"
        result_today = client.get_weather("130010", day=0)
        assert result_today["weather_code"] == "101"

        # day=1: 202.svg → "202"
        result_tomorrow = client.get_weather("130010", day=1)
        assert result_tomorrow["weather_code"] == "202"

        # day=2: 110.svg → "110"
        result_after = client.get_weather("130010", day=2)
        assert result_after["weather_code"] == "110"

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

    # パース用ヘルパーメソッドのテスト

    def test_parse_pop_normal(self):
        """正常な降水確率文字列をパースできる"""
        client = WeatherClient()
        assert client._parse_pop("30%") == 30
        assert client._parse_pop("0%") == 0
        assert client._parse_pop("100%") == 100

    def test_parse_pop_unavailable(self):
        """「--%」はNoneを返す"""
        client = WeatherClient()
        assert client._parse_pop("--%") is None

    def test_parse_pop_empty(self):
        """空文字列はNoneを返す"""
        client = WeatherClient()
        assert client._parse_pop("") is None
        assert client._parse_pop(None) is None

    def test_parse_temp_normal(self):
        """正常な気温文字列をパースできる"""
        client = WeatherClient()
        assert client._parse_temp("19") == 19
        assert client._parse_temp("0") == 0
        assert client._parse_temp("-3") == -3

    def test_parse_temp_null(self):
        """NoneはNoneを返す"""
        client = WeatherClient()
        assert client._parse_temp(None) is None

    def test_parse_temp_empty(self):
        """空文字列はNoneを返す"""
        client = WeatherClient()
        assert client._parse_temp("") is None

    def test_extract_weather_code(self):
        """image URLからweather codeを抽出できる"""
        client = WeatherClient()
        assert (
            client._extract_weather_code(
                "https://www.jma.go.jp/bosai/forecast/img/101.svg"
            )
            == "101"
        )
        assert (
            client._extract_weather_code(
                "https://www.jma.go.jp/bosai/forecast/img/202.svg"
            )
            == "202"
        )

    def test_extract_weather_code_no_match(self):
        """URLからコードを抽出できない場合は空文字列を返す"""
        client = WeatherClient()
        assert client._extract_weather_code("https://example.com/invalid") == ""
        assert client._extract_weather_code("") == ""
        assert client._extract_weather_code(None) == ""
