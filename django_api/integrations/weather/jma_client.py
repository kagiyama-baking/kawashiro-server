"""JMA (Japan Meteorological Agency) weather API client."""

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .exceptions import (
    JMAAreaNotFoundError,
    JMANetworkError,
    JMAParseError,
    JMATimeoutError,
)

JMA_API_BASE_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast"
JMA_TIMEOUT = 10
JST = ZoneInfo("Asia/Tokyo")
LATE_NIGHT_END_HOUR = 5  # 深夜帯の終了時刻（5時）

# 都道府県コード（上4桁）から都道府県名へのマッピング
PREFECTURE_NAMES = {
    "0100": "北海道",
    "0200": "青森県",
    "0300": "岩手県",
    "0400": "宮城県",
    "0500": "秋田県",
    "0600": "山形県",
    "0700": "福島県",
    "0800": "茨城県",
    "0900": "栃木県",
    "1000": "群馬県",
    "1100": "埼玉県",
    "1200": "千葉県",
    "1300": "東京都",
    "1400": "神奈川県",
    "1500": "新潟県",
    "1600": "富山県",
    "1700": "石川県",
    "1800": "福井県",
    "1900": "山梨県",
    "2000": "長野県",
    "2100": "岐阜県",
    "2200": "静岡県",
    "2300": "愛知県",
    "2400": "三重県",
    "2500": "滋賀県",
    "2600": "京都府",
    "2700": "大阪府",
    "2800": "兵庫県",
    "2900": "奈良県",
    "3000": "和歌山県",
    "3100": "鳥取県",
    "3200": "島根県",
    "3300": "岡山県",
    "3400": "広島県",
    "3500": "山口県",
    "3600": "徳島県",
    "3700": "香川県",
    "3800": "愛媛県",
    "3900": "高知県",
    "4000": "福岡県",
    "4100": "佐賀県",
    "4200": "長崎県",
    "4300": "熊本県",
    "4400": "大分県",
    "4500": "宮崎県",
    "4600": "鹿児島県",
    "4700": "沖縄県",
}


class JMAWeatherClient:
    """Client for fetching weather data from JMA API."""

    def __init__(self, timeout: int = JMA_TIMEOUT):
        self.timeout = timeout

    def _is_late_night(self, current_time: time) -> bool:
        """Check if the current time is in late night period (0:00-5:00 JST).

        Args:
            current_time: Current time to check

        Returns:
            True if in late night period, False otherwise
        """
        return current_time < time(LATE_NIGHT_END_HOUR, 0)

    def _get_adjusted_day_index(self, day: int, max_index: int = 2) -> int:
        """Get the adjusted day index for late night period.

        During late night (0:00-5:00 JST), JMA data is not yet updated,
        so we shift the index by 1 to get the correct data.
        The index is capped at max_index to avoid IndexError.

        Args:
            day: Original day parameter (0=today, 1=tomorrow, 2=day after)
            max_index: Maximum allowed index (default: 2 for short-term forecast)

        Returns:
            Adjusted index for accessing timeSeries data
        """
        now = datetime.now(JST)
        if self._is_late_night(now.time()):
            return min(day + 1, max_index)
        return day

    def get_prefecture_code(self, area_code: str) -> str:
        """Convert area code to prefecture code.

        Args:
            area_code: Sub-area code (e.g., "130010" for Tokyo)

        Returns:
            Prefecture code (e.g., "130000")
        """
        # 予報区コードの下2桁を00に置き換えて都道府県コードを生成
        # 例: 130010 -> 130000, 130020 -> 130000
        return area_code[:4] + "00"

    def fetch_forecast(self, prefecture_code: str) -> list[dict[str, Any]]:
        """Fetch raw forecast data from JMA API.

        Args:
            prefecture_code: Prefecture code (e.g., "130000" for Tokyo)

        Returns:
            Raw JSON response from JMA API

        Raises:
            JMANetworkError: Network connection error
            JMATimeoutError: Request timeout
            JMAParseError: JSON parsing error
            JMAAreaNotFoundError: 都道府県コードが見つからない (HTTP 404)
        """
        url = f"{JMA_API_BASE_URL}/{prefecture_code}.json"

        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            # HTTP 404 は存在しない都道府県コードを示す
            if e.response is not None and e.response.status_code == 404:
                raise JMAAreaNotFoundError(
                    f"指定された都道府県コード '{prefecture_code}' が見つかりません"
                ) from e
            # その他のHTTPエラー（500, 503など）はネットワークエラーとして扱う
            raise JMANetworkError("気象庁APIへの接続に失敗しました") from e
        except requests.ConnectionError as e:
            raise JMANetworkError("気象庁APIへの接続に失敗しました") from e
        except requests.Timeout as e:
            raise JMATimeoutError(
                "気象庁APIへのリクエストがタイムアウトしました"
            ) from e
        except ValueError as e:
            raise JMAParseError("気象庁APIのレスポンスの解析に失敗しました") from e

    def _find_area_index(
        self, areas: list[dict[str, Any]], area_code: str
    ) -> int | None:
        """Find the index of the specified area in the areas list.

        Args:
            areas: List of area data from API response
            area_code: Target area code

        Returns:
            Index of the area, or None if not found
        """
        for i, area in enumerate(areas):
            if area.get("area", {}).get("code") == area_code:
                return i
        return None

    def _get_prefecture_name(self, area_code: str) -> str | None:
        """Get prefecture name from area code using mapping table.

        Args:
            area_code: Sub-area code (e.g., "130010" for Tokyo)

        Returns:
            Prefecture name or None if not found
        """
        # 地域コードの上4桁から都道府県名を取得
        prefecture_key = area_code[:4]
        return PREFECTURE_NAMES.get(prefecture_key)

    def get_weather(self, area_code: str, day: int = 0) -> dict[str, Any]:
        """Get weather forecast for a specific day and area.

        Args:
            area_code: Sub-area code (e.g., "130010" for Tokyo)
            day: 0 for today, 1 for tomorrow, 2 for day after tomorrow

        Returns:
            Dictionary containing weather data

        Raises:
            JMAAreaNotFoundError: 予報区コードが見つからない
        """
        # 予報区コードから都道府県コードを導出
        prefecture_code = self.get_prefecture_code(area_code)
        raw_data = self.fetch_forecast(prefecture_code)

        # 都道府県名を取得
        prefecture_name = self._get_prefecture_name(area_code)

        # 深夜帯（0時〜5時）の場合、インデックスを1つシフト
        adjusted_day = self._get_adjusted_day_index(day)

        # 短期予報（3日間）は最初の要素
        short_term = raw_data[0]
        time_series = short_term["timeSeries"]

        # 天気情報（timeSeries[0]）
        weather_series = time_series[0]
        weather_areas = weather_series["areas"]

        # 指定された予報区を検索
        area_idx = self._find_area_index(weather_areas, area_code)
        if area_idx is None:
            raise JMAAreaNotFoundError(
                f"指定された予報区コード '{area_code}' が見つかりません"
            )

        weather_area = weather_areas[area_idx]
        sub_area_name = weather_area["area"]["name"]
        area_code_detail = weather_area["area"]["code"]
        weather = weather_area["weathers"][adjusted_day]
        weather_code = weather_area["weatherCodes"][adjusted_day]

        # 地域名を「都道府県名 地域名」の形式で構築
        if prefecture_name:
            area_name = f"{prefecture_name} {sub_area_name}"
        else:
            area_name = sub_area_name

        # 日付を計算
        time_defines = weather_series["timeDefines"]
        date_str = time_defines[adjusted_day][:10]

        # 降水確率（timeSeries[1]）
        pop_series = time_series[1]
        pop_areas = pop_series["areas"]

        # 降水確率も同じエリアを検索
        pop_area_idx = self._find_area_index(pop_areas, area_code)
        pops = []
        if pop_area_idx is not None:
            pops = pop_areas[pop_area_idx].get("pops", [])

        # 降水確率のマッピング（時間帯別）
        pop_00_06 = None
        pop_06_12 = None
        pop_12_18 = None
        pop_18_24 = None

        # 深夜帯かどうかを判定
        now = datetime.now(JST)
        is_late_night = self._is_late_night(now.time())

        if adjusted_day == 0:
            # 今日の場合：18時からの降水確率のみ（最初の値）
            if len(pops) > 0:
                pop_18_24 = self._parse_pop(pops[0])
        elif adjusted_day == 1:
            # 明日の場合：4つの時間帯
            # popsの順序: 今日18時, 明日0時, 明日6時, 明日12時, 明日18時
            if len(pops) > 1:
                pop_00_06 = self._parse_pop(pops[1])
            if len(pops) > 2:
                pop_06_12 = self._parse_pop(pops[2])
            if len(pops) > 3:
                pop_12_18 = self._parse_pop(pops[3])
            if len(pops) > 4:
                pop_18_24 = self._parse_pop(pops[4])

        # 気温（timeSeries[2]）- 明日の最低/最高気温
        temp_min = None
        temp_max = None

        if len(time_series) > 2:
            temp_series = time_series[2]
            if "areas" in temp_series and len(temp_series["areas"]) > 0:
                temp_area = temp_series["areas"][0]
                temps = temp_area.get("temps", [])
                if adjusted_day == 1 and len(temps) >= 2:
                    # 明日の気温: temps[0]が最低、temps[1]が最高
                    temp_min = self._parse_temp(temps[0])
                    temp_max = self._parse_temp(temps[1])

        # 週間予報からの気温と降水確率
        # 明後日以降、または深夜帯の場合は週間予報から取得
        use_weekly = adjusted_day >= 2 or (is_late_night and day >= 1)
        if use_weekly and len(raw_data) > 1:
            weekly = raw_data[1]
            weekly_series = weekly["timeSeries"]

            # 週間予報のインデックス
            # 深夜帯の場合: day=0→インデックス0(明日), day=1→インデックス1(明後日)
            # 通常時の場合: day=2→インデックス1(明後日)
            weekly_idx = day if is_late_night else adjusted_day - 1

            # 降水確率（timeSeries[0]）- 全時間帯に同じ値を設定
            if len(weekly_series) > 0:
                pop_weekly = weekly_series[0]
                if "areas" in pop_weekly and len(pop_weekly["areas"]) > 0:
                    pop_area = pop_weekly["areas"][0]
                    weekly_pops = pop_area.get("pops", [])
                    if len(weekly_pops) > weekly_idx:
                        daily_pop = self._parse_pop(weekly_pops[weekly_idx])
                        # 深夜帯のday=0は降水確率を上書きしない（短期予報を使用）
                        if not (is_late_night and day == 0):
                            pop_00_06 = daily_pop
                            pop_06_12 = daily_pop
                            pop_12_18 = daily_pop
                            pop_18_24 = daily_pop

            # 気温（timeSeries[1]）
            if len(weekly_series) > 1:
                temp_weekly = weekly_series[1]
                if "areas" in temp_weekly and len(temp_weekly["areas"]) > 0:
                    temp_area = temp_weekly["areas"][0]
                    temps_min = temp_area.get("tempsMin", [])
                    temps_max = temp_area.get("tempsMax", [])
                    if len(temps_min) > weekly_idx:
                        parsed_min = self._parse_temp(temps_min[weekly_idx])
                        if parsed_min is not None:
                            temp_min = parsed_min
                    if len(temps_max) > weekly_idx:
                        parsed_max = self._parse_temp(temps_max[weekly_idx])
                        if parsed_max is not None:
                            temp_max = parsed_max

        return {
            "area_name": area_name,
            "area_code": area_code_detail,
            "date": date_str,
            "weather": weather,
            "weather_code": weather_code,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "pop_00_06": pop_00_06,
            "pop_06_12": pop_06_12,
            "pop_12_18": pop_12_18,
            "pop_18_24": pop_18_24,
        }

    def _parse_pop(self, value: str) -> int | None:
        """Parse precipitation probability value."""
        if value == "" or value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _parse_temp(self, value: str) -> int | None:
        """Parse temperature value."""
        if value == "" or value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
