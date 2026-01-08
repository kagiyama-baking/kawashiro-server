"""Tests for Yahoo transit diainfo client."""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from train.exceptions import (
    YahooNetworkError,
    YahooParseError,
    YahooRailNotFoundError,
    YahooTimeoutError,
)
from train.yahoo_client import YahooTransitClient


class TestYahooTransitClient:
    """Tests for YahooTransitClient."""

    @pytest.fixture
    def sample_normal_html(self):
        """平常運転時のサンプルHTMLレスポンス"""
        next_data = {
            "props": {
                "pageProps": {
                    "diainfoTrainFeature": {
                        "routeInfo": {
                            "displayName": "都営大江戸線",
                            "displayYomi": "とえいおおえどせん",
                            "companyName": "東京都交通局",
                            "railAreaName": "関東",
                        },
                        "diainfo": [
                            {
                                "status": "平常運転",
                                "message": "現在､事故･遅延に関する情報はありません。",
                                "causeCode": None,
                                "causeName": None,
                                "updateDate": "2026-01-08 09:00:00",
                            }
                        ],
                    }
                }
            }
        }
        return f"""
        <html>
        <head><title>都営大江戸線の運行情報</title></head>
        <body>
        <script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>
        </body>
        </html>
        """

    @pytest.fixture
    def sample_delayed_html(self):
        """遅延時のサンプルHTMLレスポンス"""
        next_data = {
            "props": {
                "pageProps": {
                    "diainfoTrainFeature": {
                        "routeInfo": {
                            "displayName": "京浜東北根岸線",
                            "displayYomi": "けいひんとうほくねぎしせん",
                            "companyName": "JR東日本",
                            "railAreaName": "関東",
                        },
                        "diainfo": [
                            {
                                "status": "列車遅延",
                                "message": "混雑の影響で、一部列車に遅れが出ています。",
                                "causeCode": "5017",
                                "causeName": "混雑",
                                "updateDate": "2026-01-08 08:55:00",
                                "impactRange": "上下方面[全区間]",
                            }
                        ],
                    }
                }
            }
        }
        return f"""
        <html>
        <head><title>京浜東北根岸線の運行情報</title></head>
        <body>
        <script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>
        </body>
        </html>
        """

    @pytest.fixture
    def sample_suspended_html(self):
        """運転見合わせ時のサンプルHTMLレスポンス"""
        next_data = {
            "props": {
                "pageProps": {
                    "diainfoTrainFeature": {
                        "routeInfo": {
                            "displayName": "山手線",
                            "displayYomi": "やまのてせん",
                            "companyName": "JR東日本",
                            "railAreaName": "関東",
                        },
                        "diainfo": [
                            {
                                "status": "運転見合わせ",
                                "message": "人身事故の影響で、運転を見合わせています。",
                                "causeCode": "1001",
                                "causeName": "人身事故",
                                "updateDate": "2026-01-08 10:00:00",
                                "impactRange": "全線",
                            }
                        ],
                    }
                }
            }
        }
        return f"""
        <html>
        <head><title>山手線の運行情報</title></head>
        <body>
        <script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>
        </body>
        </html>
        """

    def test_build_url(self):
        """URLが正しく構築される"""
        client = YahooTransitClient()
        assert client._build_url("131") == "https://transit.yahoo.co.jp/diainfo/131/0"
        assert client._build_url("22") == "https://transit.yahoo.co.jp/diainfo/22/0"

    @patch("train.yahoo_client.requests.get")
    def test_fetch_diainfo_success_normal(self, mock_get, sample_normal_html):
        """平常運転の運行情報を正常に取得できる"""
        mock_response = Mock()
        mock_response.text = sample_normal_html
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = YahooTransitClient()
        result = client.fetch_diainfo("131")

        assert result["rail_name"] == "都営大江戸線"
        assert result["company_name"] == "東京都交通局"
        assert result["status"] == "平常運転"
        assert result["is_delayed"] is False
        assert result["message"] == "現在､事故･遅延に関する情報はありません。"
        assert result["cause"] is None
        assert result["update_time"] == "2026-01-08 09:00:00"

    @patch("train.yahoo_client.requests.get")
    def test_fetch_diainfo_success_delayed(self, mock_get, sample_delayed_html):
        """遅延時の運行情報を正常に取得できる"""
        mock_response = Mock()
        mock_response.text = sample_delayed_html
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = YahooTransitClient()
        result = client.fetch_diainfo("22")

        assert result["rail_name"] == "京浜東北根岸線"
        assert result["company_name"] == "JR東日本"
        assert result["status"] == "列車遅延"
        assert result["is_delayed"] is True
        assert result["message"] == "混雑の影響で、一部列車に遅れが出ています。"
        assert result["cause"] == "混雑"
        assert result["update_time"] == "2026-01-08 08:55:00"

    @patch("train.yahoo_client.requests.get")
    def test_fetch_diainfo_success_suspended(self, mock_get, sample_suspended_html):
        """運転見合わせ時の運行情報を正常に取得できる"""
        mock_response = Mock()
        mock_response.text = sample_suspended_html
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = YahooTransitClient()
        result = client.fetch_diainfo("35")

        assert result["rail_name"] == "山手線"
        assert result["status"] == "運転見合わせ"
        assert result["is_delayed"] is True
        assert result["cause"] == "人身事故"

    @patch("train.yahoo_client.requests.get")
    def test_fetch_diainfo_network_error(self, mock_get):
        """ネットワークエラー時にYahooNetworkErrorを発生させる"""
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        client = YahooTransitClient()

        with pytest.raises(YahooNetworkError):
            client.fetch_diainfo("131")

    @patch("train.yahoo_client.requests.get")
    def test_fetch_diainfo_timeout_error(self, mock_get):
        """タイムアウト時にYahooTimeoutErrorを発生させる"""
        mock_get.side_effect = requests.Timeout("Request timed out")

        client = YahooTransitClient()

        with pytest.raises(YahooTimeoutError):
            client.fetch_diainfo("131")

    @patch("train.yahoo_client.requests.get")
    def test_fetch_diainfo_http_404_error(self, mock_get):
        """存在しない路線IDの場合（HTTP 404）にYahooRailNotFoundErrorを発生させる"""
        mock_response = Mock()
        mock_response.status_code = 404
        http_error = requests.HTTPError("404 Client Error: Not Found")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response

        client = YahooTransitClient()

        with pytest.raises(YahooRailNotFoundError):
            client.fetch_diainfo("99999")

    @patch("train.yahoo_client.requests.get")
    def test_fetch_diainfo_parse_error_no_next_data(self, mock_get):
        """__NEXT_DATA__が存在しない場合にYahooParseErrorを発生させる"""
        mock_response = Mock()
        mock_response.text = "<html><body>No data</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = YahooTransitClient()

        with pytest.raises(YahooParseError):
            client.fetch_diainfo("131")

    @patch("train.yahoo_client.requests.get")
    def test_fetch_diainfo_parse_error_invalid_json(self, mock_get):
        """JSONが不正な場合にYahooParseErrorを発生させる"""
        mock_response = Mock()
        mock_response.text = """
        <html>
        <script id="__NEXT_DATA__" type="application/json">invalid json</script>
        </html>
        """
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = YahooTransitClient()

        with pytest.raises(YahooParseError):
            client.fetch_diainfo("131")

    @patch("train.yahoo_client.requests.get")
    def test_fetch_multiple_rails(
        self, mock_get, sample_normal_html, sample_delayed_html
    ):
        """複数の路線情報を一括取得できる"""
        mock_response_normal = Mock()
        mock_response_normal.text = sample_normal_html
        mock_response_normal.raise_for_status = Mock()

        mock_response_delayed = Mock()
        mock_response_delayed.text = sample_delayed_html
        mock_response_delayed.raise_for_status = Mock()

        mock_get.side_effect = [mock_response_normal, mock_response_delayed]

        client = YahooTransitClient()
        results = client.fetch_multiple_diainfo(["131", "22"])

        assert len(results) == 2
        assert results[0]["rail_name"] == "都営大江戸線"
        assert results[0]["is_delayed"] is False
        assert results[1]["rail_name"] == "京浜東北根岸線"
        assert results[1]["is_delayed"] is True

    @patch("train.yahoo_client.requests.get")
    def test_fetch_multiple_rails_with_error(self, mock_get, sample_normal_html):
        """複数取得時に一部でエラーが発生しても他の結果は返す"""
        mock_response_normal = Mock()
        mock_response_normal.text = sample_normal_html
        mock_response_normal.raise_for_status = Mock()

        mock_get.side_effect = [
            mock_response_normal,
            requests.Timeout("timeout"),
        ]

        client = YahooTransitClient()
        results = client.fetch_multiple_diainfo(["131", "22"])

        assert len(results) == 2
        assert results[0]["rail_name"] == "都営大江戸線"
        assert results[0]["error"] is None
        assert results[1]["rail_id"] == "22"
        assert results[1]["error"] is not None
