"""Tests for train views."""

from unittest.mock import Mock, patch

from rest_framework import status

from train.exceptions import (
    YahooNetworkError,
    YahooParseError,
    YahooRailNotFoundError,
    YahooTimeoutError,
)


class TestDiainfoView:
    """Tests for DiainfoView."""

    @staticmethod
    def diainfo_data(rail_id="131", rail_name="都営大江戸線", is_delayed=False):
        """サンプル運行情報データ"""
        return {
            "rail_id": rail_id,
            "rail_name": rail_name,
            "company_name": "東京都交通局",
            "status": "平常運転" if not is_delayed else "列車遅延",
            "is_delayed": is_delayed,
            "message": "現在､事故･遅延に関する情報はありません。"
            if not is_delayed
            else "混雑の影響で、一部列車に遅れが出ています。",
            "cause": None if not is_delayed else "混雑",
            "update_time": "2026-01-08 09:00:00",
            "error": None,
        }

    @patch("train.views.YahooTransitClient")
    def test_get_diainfo_single_rail(self, mock_client_class, authenticated_client):
        """単一の路線運行情報を取得できる"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.fetch_multiple_diainfo.return_value = [self.diainfo_data()]

        response = authenticated_client.get("/train/diainfo/", {"rail_ids": "131"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["rail_name"] == "都営大江戸線"
        assert response.data[0]["is_delayed"] is False
        mock_client.fetch_multiple_diainfo.assert_called_once_with(["131"])

    @patch("train.views.YahooTransitClient")
    def test_get_diainfo_multiple_rails(self, mock_client_class, authenticated_client):
        """複数の路線運行情報を取得できる"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.fetch_multiple_diainfo.return_value = [
            self.diainfo_data("131", "都営大江戸線", False),
            self.diainfo_data("22", "京浜東北根岸線", True),
        ]

        response = authenticated_client.get("/train/diainfo/", {"rail_ids": "131,22"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert response.data[0]["rail_name"] == "都営大江戸線"
        assert response.data[1]["rail_name"] == "京浜東北根岸線"
        assert response.data[1]["is_delayed"] is True

    def test_get_diainfo_missing_rail_ids(self, authenticated_client):
        """rail_idsが指定されていない場合は400エラー"""
        response = authenticated_client.get("/train/diainfo/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "rail_ids" in response.data

    def test_get_diainfo_empty_rail_ids(self, authenticated_client):
        """rail_idsが空の場合は400エラー"""
        response = authenticated_client.get("/train/diainfo/", {"rail_ids": ""})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "rail_ids" in response.data

    @patch("train.views.YahooTransitClient")
    def test_get_diainfo_network_error(self, mock_client_class, authenticated_client):
        """ネットワークエラー時は502を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.fetch_multiple_diainfo.side_effect = YahooNetworkError(
            "Network error"
        )

        response = authenticated_client.get("/train/diainfo/", {"rail_ids": "131"})

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("train.views.YahooTransitClient")
    def test_get_diainfo_timeout_error(self, mock_client_class, authenticated_client):
        """タイムアウト時は504を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.fetch_multiple_diainfo.side_effect = YahooTimeoutError("Timeout")

        response = authenticated_client.get("/train/diainfo/", {"rail_ids": "131"})

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "error" in response.data

    @patch("train.views.YahooTransitClient")
    def test_get_diainfo_parse_error(self, mock_client_class, authenticated_client):
        """パースエラー時は502を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.fetch_multiple_diainfo.side_effect = YahooParseError("Parse error")

        response = authenticated_client.get("/train/diainfo/", {"rail_ids": "131"})

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("train.views.YahooTransitClient")
    def test_get_diainfo_rail_not_found(self, mock_client_class, authenticated_client):
        """路線IDが見つからない場合は404を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.fetch_multiple_diainfo.side_effect = YahooRailNotFoundError(
            "Rail not found"
        )

        response = authenticated_client.get("/train/diainfo/", {"rail_ids": "99999"})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    @patch("train.views.YahooTransitClient")
    def test_get_diainfo_partial_error_in_response(
        self, mock_client_class, authenticated_client
    ):
        """一部の路線でエラーが発生しても全体は200を返す"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.fetch_multiple_diainfo.return_value = [
            self.diainfo_data("131", "都営大江戸線", False),
            {
                "rail_id": "99999",
                "rail_name": None,
                "company_name": None,
                "status": None,
                "is_delayed": None,
                "message": None,
                "cause": None,
                "update_time": None,
                "error": "路線IDが見つかりません",
            },
        ]

        response = authenticated_client.get(
            "/train/diainfo/", {"rail_ids": "131,99999"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert response.data[0]["rail_name"] == "都営大江戸線"
        assert response.data[1]["error"] == "路線IDが見つかりません"

    def test_get_diainfo_unauthenticated(self, api_client):
        """認証なしではアクセスできない"""
        response = api_client.get("/train/diainfo/", {"rail_ids": "131"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
