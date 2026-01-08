"""Yahoo Transit diainfo client for scraping train operation status."""

import json
import re

import requests

from train.exceptions import (
    YahooNetworkError,
    YahooParseError,
    YahooRailNotFoundError,
    YahooTimeoutError,
)


class YahooTransitClient:
    """Yahoo!乗換案内の運行情報をスクレイピングするクライアント"""

    BASE_URL = "https://transit.yahoo.co.jp/diainfo"
    NORMAL_STATUSES = ["平常運転"]
    DEFAULT_TIMEOUT = 10
    # ボット検知回避のためブラウザらしいUser-Agentを設定
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
    }

    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    def _build_url(self, rail_id: str) -> str:
        """運行情報ページのURLを構築する"""
        return f"{self.BASE_URL}/{rail_id}/0"

    def _parse_next_data(self, html: str) -> dict:
        """HTMLから__NEXT_DATA__のJSONを抽出してパースする"""
        pattern = r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            raise YahooParseError("__NEXT_DATA__が見つかりません")

        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise YahooParseError(f"JSONのパースに失敗しました: {e}") from e

    def _extract_diainfo(self, next_data: dict, rail_id: str) -> dict:
        """__NEXT_DATA__から運行情報を抽出する"""
        try:
            page_props = next_data["props"]["pageProps"]
            feature = page_props["diainfoTrainFeature"]
            route_info = feature["routeInfo"]

            # routeInfoは直接またはpropertyの中にある
            if "property" in route_info:
                route_props = route_info["property"]
            else:
                route_props = route_info

            # diainfoはfeature直下またはroute_props内にある
            diainfo_list = feature.get("diainfo") or route_props.get("diainfo")

            if diainfo_list and len(diainfo_list) > 0:
                diainfo = diainfo_list[0]
                status = diainfo.get("status", "不明")
                message = diainfo.get("message")
                cause = diainfo.get("causeName")
                update_time = diainfo.get("updateDate")
            else:
                # 平常運転時はdiainfoがない
                status = "平常運転"
                # shareMessageからメッセージを取得
                share_message = page_props.get("shareMessage", "")
                # 括弧内の時刻情報を除去してメッセージのみ取得
                if "（" in share_message:
                    message = share_message.split("（")[0]
                else:
                    message = share_message
                cause = None
                update_time = page_props.get("updateTimeText")

            is_delayed = status not in self.NORMAL_STATUSES

            return {
                "rail_id": rail_id,
                "rail_name": route_props.get("displayName"),
                "company_name": route_props.get("companyName"),
                "status": status,
                "is_delayed": is_delayed,
                "message": message,
                "cause": cause,
                "update_time": update_time,
                "error": None,
            }
        except (KeyError, IndexError, TypeError) as e:
            raise YahooParseError(f"運行情報の抽出に失敗しました: {e}") from e

    def fetch_diainfo(self, rail_id: str) -> dict:
        """指定された路線IDの運行情報を取得する"""
        url = self._build_url(rail_id)

        try:
            response = requests.get(
                url, timeout=self.timeout, headers=self.DEFAULT_HEADERS
            )
            response.raise_for_status()
        except requests.ConnectionError as e:
            raise YahooNetworkError(f"接続エラー: {e}") from e
        except requests.Timeout as e:
            raise YahooTimeoutError(f"タイムアウト: {e}") from e
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                raise YahooRailNotFoundError(
                    f"路線ID '{rail_id}' が見つかりません"
                ) from e
            raise YahooNetworkError(f"HTTPエラー: {e}") from e

        next_data = self._parse_next_data(response.text)
        return self._extract_diainfo(next_data, rail_id)

    def fetch_multiple_diainfo(self, rail_ids: list[str]) -> list[dict]:
        """複数の路線IDの運行情報を一括取得する"""
        results = []
        for rail_id in rail_ids:
            try:
                result = self.fetch_diainfo(rail_id)
                results.append(result)
            except (
                YahooNetworkError,
                YahooTimeoutError,
                YahooParseError,
                YahooRailNotFoundError,
            ) as e:
                results.append(
                    {
                        "rail_id": rail_id,
                        "rail_name": None,
                        "company_name": None,
                        "status": None,
                        "is_delayed": None,
                        "message": None,
                        "cause": None,
                        "update_time": None,
                        "error": str(e),
                    }
                )
        return results
