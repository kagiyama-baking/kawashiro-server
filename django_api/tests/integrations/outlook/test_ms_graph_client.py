"""OutlookGraphClientのテスト"""

from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.outlook.exceptions import CalendarError


@pytest.fixture
def mock_outlook_graph_settings():
    """OutlookGraphSettings用のモックフィクスチャ"""
    from integrations.msgraph.config import MSGraphSettings

    settings = MSGraphSettings(
        tenant_id="test-tenant",
        client_id="test-client",
        cert_thumbprint="test-thumb",
        private_key="-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----",
        target_user="test@example.com",
    )

    with patch(
        "integrations.msgraph.base.get_ms_graph_settings", return_value=settings
    ):
        yield settings


@pytest.fixture
def outlook_client(mock_outlook_graph_settings):
    """モック設定を使用したOutlookMSGraphClientのフィクスチャ"""
    from integrations.msgraph import OutlookMSGraphClient

    client = OutlookMSGraphClient()
    client._access_token = "test-token"
    return client


class TestOutlookMSGraphClientInit:
    """OutlookMSGraphClientの初期化テスト"""

    def test_init_success(self, mock_outlook_graph_settings):
        """正常に初期化できること"""
        from integrations.msgraph import OutlookMSGraphClient

        client = OutlookMSGraphClient()

        assert client.tenant_id == "test-tenant"
        assert client.client_id == "test-client"
        assert client.target_user == "test@example.com"

    def test_init_with_configuration_error(self):
        """設定エラー時に例外が発生すること"""
        from integrations.msgraph import OutlookMSGraphClient

        with (
            patch(
                "integrations.msgraph.base.get_ms_graph_settings",
                side_effect=ConfigurationError("Missing config"),
            ),
            pytest.raises(ConfigurationError),
        ):
            OutlookMSGraphClient()


class TestGetCalendarEvents:
    """get_calendar_eventsメソッドのテスト"""

    def test_get_events_success(self, outlook_client):
        """カレンダーイベントを正常に取得できること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "event-123",
                    "subject": "テスト会議",
                    "start": {
                        "dateTime": "2025-12-23T10:00:00",
                        "timeZone": "Asia/Tokyo",
                    },
                    "end": {
                        "dateTime": "2025-12-23T11:00:00",
                        "timeZone": "Asia/Tokyo",
                    },
                    "isAllDay": False,
                }
            ]
        }
        mock_response.raise_for_status = Mock()

        with patch.object(
            outlook_client._session, "get", return_value=mock_response
        ) as mock_get:
            events = outlook_client.get_calendar_events(
                start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
            )

            assert len(events) == 1
            assert events[0]["subject"] == "テスト会議"
            mock_get.assert_called_once()

    def test_get_events_empty(self, outlook_client):
        """イベントがない場合は空リストを返すこと"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": []}
        mock_response.raise_for_status = Mock()

        with patch.object(outlook_client._session, "get", return_value=mock_response):
            events = outlook_client.get_calendar_events(
                start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
            )

            assert events == []

    def test_get_events_with_timeout(self, outlook_client):
        """タイムアウト時にNetworkErrorを発生させること"""
        with patch.object(
            outlook_client._session,
            "get",
            side_effect=requests.exceptions.Timeout("Timeout"),
        ):
            with pytest.raises(NetworkError) as exc_info:
                outlook_client.get_calendar_events(
                    start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
                )

            assert "タイムアウト" in str(exc_info.value)

    def test_get_events_with_connection_error(self, outlook_client):
        """接続エラー時にNetworkErrorを発生させること"""
        with patch.object(
            outlook_client._session,
            "get",
            side_effect=requests.exceptions.ConnectionError("Connection refused"),
        ):
            with pytest.raises(NetworkError) as exc_info:
                outlook_client.get_calendar_events(
                    start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
                )

            assert "接続に失敗" in str(exc_info.value)

    def test_get_events_with_401_error(self, outlook_client):
        """401エラー時にAuthenticationErrorを発生させること"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        with (
            patch.object(outlook_client._session, "get", return_value=mock_response),
            pytest.raises(AuthenticationError),
        ):
            outlook_client.get_calendar_events(
                start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
            )

    def test_get_events_with_other_http_error(self, outlook_client):
        """その他のHTTPエラー時にCalendarErrorを発生させること"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        with (
            patch.object(outlook_client._session, "get", return_value=mock_response),
            pytest.raises(CalendarError),
        ):
            outlook_client.get_calendar_events(
                start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
            )


class TestAcquireToken:
    """acquire_tokenメソッドのテスト"""

    def test_acquire_token_success(self, outlook_client):
        """トークンを正常に取得できること"""
        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "new-test-token"
        }

        with patch(
            "integrations.msgraph.base.ConfidentialClientApplication",
            return_value=mock_app,
        ):
            token = outlook_client.acquire_token()

            assert token == "new-test-token"
            assert outlook_client._access_token == "new-test-token"

    def test_acquire_token_failure(self, outlook_client):
        """トークン取得失敗時にAuthenticationErrorを発生させること"""
        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "Invalid client credentials",
        }

        with patch(
            "integrations.msgraph.base.ConfidentialClientApplication",
            return_value=mock_app,
        ):
            with pytest.raises(AuthenticationError) as exc_info:
                outlook_client.acquire_token()

            assert "Invalid client credentials" in str(exc_info.value)
