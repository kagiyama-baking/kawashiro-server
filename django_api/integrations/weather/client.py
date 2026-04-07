"""天気予報クライアント（tsukumijima.net API）."""

import re
from typing import Any

import requests

from .exceptions import (
    WeatherAreaNotFoundError,
    WeatherNetworkError,
    WeatherParseError,
    WeatherTimeoutError,
)

API_BASE_URL = "https://weather.tsukumijima.net/api/forecast/city"
DEFAULT_TIMEOUT = 10


class WeatherClient:
    """tsukumijima.net 天気予報APIクライアント."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """クライアントを初期化."""
        self.timeout = timeout

    def fetch_forecast(self, area_code: str) -> dict[str, Any]:
        """指定地域の天気予報データを取得.

        Args:
            area_code: 6桁の地域コード（例: "130010"）

        Returns:
            APIレスポンスのJSON辞書

        Raises:
            WeatherAreaNotFoundError: 地域コードが存在しない場合
            WeatherNetworkError: ネットワークエラー
            WeatherTimeoutError: タイムアウト
            WeatherParseError: JSONパースエラー
        """
        url = f"{API_BASE_URL}/{area_code}"
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.Timeout as e:
            raise WeatherTimeoutError(
                f"天気予報APIへのリクエストがタイムアウトしました: {e}"
            ) from e
        except requests.ConnectionError as e:
            raise WeatherNetworkError(f"天気予報APIへの接続に失敗しました: {e}") from e
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                raise WeatherAreaNotFoundError(
                    f"地域コード '{area_code}' が見つかりません"
                ) from e
            raise WeatherNetworkError(
                f"天気予報APIからエラーレスポンスが返されました: {e}"
            ) from e
        except (ValueError, KeyError) as e:
            raise WeatherParseError(
                f"天気予報APIのレスポンス解析に失敗しました: {e}"
            ) from e

    def get_weather(self, area_code: str, day: int = 0) -> dict[str, Any]:
        """指定地域・日付の天気予報を取得.

        Args:
            area_code: 6桁の地域コード（例: "130010"）
            day: 予報日（0=今日, 1=明日, 2=明後日）

        Returns:
            天気予報データの辞書:
                area_name: 地域名（例: "東京都 東京地方"）
                area_code: 地域コード
                date: 日付（YYYY-MM-DD）
                weather: 天気概況
                weather_code: 天気コード
                temp_min: 最低気温（℃）またはNone
                temp_max: 最高気温（℃）またはNone
                pop_00_06: 降水確率 0-6時（%）またはNone
                pop_06_12: 降水確率 6-12時（%）またはNone
                pop_12_18: 降水確率 12-18時（%）またはNone
                pop_18_24: 降水確率 18-24時（%）またはNone

        Raises:
            WeatherAreaNotFoundError: 地域コードが存在しない場合
            WeatherParseError: レスポンスの解析に失敗した場合
            WeatherNetworkError: ネットワークエラー
            WeatherTimeoutError: タイムアウト
        """
        data = self.fetch_forecast(area_code)

        try:
            forecasts = data["forecasts"]
        except (KeyError, TypeError) as e:
            raise WeatherParseError(f"天気予報データの形式が不正です: {e}") from e

        if day < 0 or day >= len(forecasts):
            raise WeatherParseError(
                f"予報日 {day} は範囲外です（0〜{len(forecasts) - 1}）"
            )

        forecast = forecasts[day]
        location = data.get("location", {})

        # 地域名を構築
        prefecture = location.get("prefecture", "")
        district = location.get("district", "")
        area_name = (
            f"{prefecture} {district}"
            if prefecture and district
            else prefecture or district
        )

        # 天気概況（detail.weatherがnullならtelopにフォールバック）
        detail = forecast.get("detail", {})
        weather = detail.get("weather") or forecast.get("telop", "")

        # 天気コード（image URLから抽出）
        image = forecast.get("image", {})
        weather_code = self._extract_weather_code(image.get("url"))

        # 気温
        temperature = forecast.get("temperature", {})
        temp_min_data = temperature.get("min", {})
        temp_max_data = temperature.get("max", {})
        temp_min = self._parse_temp(
            temp_min_data.get("celsius") if temp_min_data else None
        )
        temp_max = self._parse_temp(
            temp_max_data.get("celsius") if temp_max_data else None
        )

        # 降水確率
        chance_of_rain = forecast.get("chanceOfRain", {})

        return {
            "area_name": area_name,
            "area_code": area_code,
            "date": forecast.get("date", ""),
            "weather": weather,
            "weather_code": weather_code,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "pop_00_06": self._parse_pop(chance_of_rain.get("T00_06")),
            "pop_06_12": self._parse_pop(chance_of_rain.get("T06_12")),
            "pop_12_18": self._parse_pop(chance_of_rain.get("T12_18")),
            "pop_18_24": self._parse_pop(chance_of_rain.get("T18_24")),
        }

    def _parse_pop(self, value: str | None) -> int | None:
        """降水確率文字列をパース.

        Args:
            value: "30%", "--%", None等

        Returns:
            整数値またはNone
        """
        if not value or value == "--%":
            return None
        try:
            return int(value.replace("%", ""))
        except (ValueError, AttributeError):
            return None

    def _parse_temp(self, value: str | None) -> int | None:
        """気温文字列をパース.

        Args:
            value: "19", "-3", None等

        Returns:
            整数値またはNone
        """
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _extract_weather_code(self, url: str | None) -> str:
        """image URLからweather codeを抽出.

        tsukumijima.net APIは天気コードを直接返さないため、
        JMA公式アイコンURL（例: .../img/101.svg）のファイル名から抽出する。

        Args:
            url: "https://www.jma.go.jp/bosai/forecast/img/101.svg"

        Returns:
            天気コード文字列（例: "101"）、抽出できない場合は空文字列
        """
        if not url:
            return ""
        match = re.search(r"/(\d+)\.svg", url)
        return match.group(1) if match else ""
