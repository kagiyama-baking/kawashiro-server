"""Tests for weather views."""

from unittest.mock import Mock, patch

import pytest
from rest_framework import status

from integrations.weather.exceptions import (
    WeatherAreaNotFoundError,
    WeatherNetworkError,
    WeatherParseError,
    WeatherTimeoutError,
)

pytestmark = pytest.mark.django_db


class TestWeatherForecastView:
    """Tests for WeatherForecastView."""

    @staticmethod
    def weather_data():
        """サンプル天気データ"""
        return {
            "area_name": "東京都 東京地方",
            "area_code": "130010",
            "date": "2025-12-24",
            "weather": "晴れ　夜　くもり",
            "weather_code": "111",
            "temp_min": 4,
            "temp_max": 10,
            "pop_00_06": 10,
            "pop_06_12": 20,
            "pop_12_18": 30,
            "pop_18_24": 40,
        }

    @patch("integrations.weather.views.WeatherClient")
    def test_get_weather_success(self, mock_client_class, authenticated_client):
        """正常に天気情報を取得できる"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_weather.return_value = self.weather_data()

        response = authenticated_client.get(
            "/weather/forecast/", {"area_code": "130010", "day": 1}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["area_name"] == "東京都 東京地方"
        assert response.data["weather"] == "晴れ　夜　くもり"
        mock_client.get_weather.assert_called_once_with("130010", 1)

    @patch("integrations.weather.views.WeatherClient")
    def test_get_weather_default_day(self, mock_client_class, authenticated_client):
        """dayが指定されない場合、デフォルトで0（今日）が使用される"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_weather.return_value = self.weather_data()

        response = authenticated_client.get(
            "/weather/forecast/", {"area_code": "130010"}
        )

        assert response.status_code == status.HTTP_200_OK
        mock_client.get_weather.assert_called_once_with("130010", 0)

    def test_get_weather_missing_area_code(self, authenticated_client):
        """area_codeが指定されていない場合は400エラー"""
        response = authenticated_client.get("/weather/forecast/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "area_code" in response.data

    def test_get_weather_invalid_day(self, authenticated_client):
        """dayが無効な値の場合は400エラー"""
        response = authenticated_client.get(
            "/weather/forecast/", {"area_code": "130010", "day": 5}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "day" in response.data

    @patch("integrations.weather.views.WeatherClient")
    def test_get_weather_network_error(self, mock_client_class, authenticated_client):
        """ネットワークエラー時は502を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_weather.side_effect = WeatherNetworkError("Network error")

        response = authenticated_client.get(
            "/weather/forecast/", {"area_code": "130010"}
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("integrations.weather.views.WeatherClient")
    def test_get_weather_timeout_error(self, mock_client_class, authenticated_client):
        """タイムアウト時は504を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_weather.side_effect = WeatherTimeoutError("Timeout")

        response = authenticated_client.get(
            "/weather/forecast/", {"area_code": "130010"}
        )

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "error" in response.data

    @patch("integrations.weather.views.WeatherClient")
    def test_get_weather_parse_error(self, mock_client_class, authenticated_client):
        """パースエラー時は502を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_weather.side_effect = WeatherParseError("Parse error")

        response = authenticated_client.get(
            "/weather/forecast/", {"area_code": "130010"}
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("integrations.weather.views.WeatherClient")
    def test_get_weather_area_not_found(self, mock_client_class, authenticated_client):
        """予報区コードが見つからない場合は404を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_weather.side_effect = WeatherAreaNotFoundError("Area not found")

        response = authenticated_client.get(
            "/weather/forecast/", {"area_code": "139999"}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    def test_get_weather_unauthenticated(self, api_client):
        """認証なしではアクセスできない"""
        response = api_client.get("/weather/forecast/", {"area_code": "130010"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
