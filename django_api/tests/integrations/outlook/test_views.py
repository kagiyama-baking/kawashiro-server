"""Outlookアプリのビューテスト"""

from unittest.mock import Mock, patch

import pytest
from rest_framework import status

from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.outlook.exceptions import CalendarError

pytestmark = pytest.mark.django_db

CLIENT_PATCH = "integrations.outlook.views.OutlookMSGraphClient"

COMMON_HANDLED_ERRORS = [
    pytest.param(
        ConfigurationError("Missing configuration"),
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "サービスの設定に問題があります",
        id="ConfigurationError",
    ),
    pytest.param(
        AuthenticationError("Token expired"),
        status.HTTP_401_UNAUTHORIZED,
        "Outlookへの認証に失敗しました",
        id="AuthenticationError",
    ),
    pytest.param(
        NetworkError("Connection timeout"),
        status.HTTP_502_BAD_GATEWAY,
        "Outlookへの接続に失敗しました",
        id="NetworkError",
    ),
]


def _set_client_method_error(mock_client_class, method_name, exception):
    """クライアントメソッド呼び出し時に例外を発生させる"""
    if isinstance(exception, ConfigurationError):
        mock_client_class.side_effect = exception
        return
    mock_client = Mock()
    mock_client_class.return_value = mock_client
    getattr(mock_client, method_name).side_effect = exception


def _sample_event(**overrides):
    base = {
        "id": "event-123",
        "subject": "チーム定例",
        "start": {"dateTime": "2025-12-23T10:00:00", "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": "2025-12-23T11:00:00", "timeZone": "Asia/Tokyo"},
        "location": {"displayName": "会議室A"},
        "isAllDay": False,
        "organizer": {"emailAddress": {"address": "organizer@example.com"}},
        "webLink": "https://outlook.office365.com/event/123",
        "bodyPreview": "議題: プロジェクト進捗",
    }
    base.update(overrides)
    return base


@pytest.mark.api
class TestOutlookEventsView:
    """OutlookEventsViewのテストクラス"""

    @patch(CLIENT_PATCH)
    def test_get_events_success_default_params(
        self, mock_client_class, authenticated_client
    ):
        """デフォルトパラメータで予定一覧の取得が成功し、レスポンス形式が正しいこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.return_value = [_sample_event()]

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_200_OK
        for key in ("start_date", "end_date", "count", "events"):
            assert key in response.data
        assert response.data["count"] == 1

        event = response.data["events"][0]
        assert event["subject"] == "チーム定例"
        for key in (
            "id",
            "subject",
            "start",
            "end",
            "location",
            "is_all_day",
            "organizer",
            "web_link",
            "body_preview",
        ):
            assert key in event

    @patch(CLIENT_PATCH)
    def test_get_events_with_days_parameter(
        self, mock_client_class, authenticated_client
    ):
        """daysパラメータを指定して予定一覧を取得できること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.return_value = []

        response = authenticated_client.get("/outlook/events/?days=7")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0
        mock_client.get_calendar_events.assert_called_once()

    @patch(CLIENT_PATCH)
    def test_get_events_with_start_date_and_end_date(
        self, mock_client_class, authenticated_client
    ):
        """start_dateとend_dateで予定一覧を取得できること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.return_value = []

        response = authenticated_client.get(
            "/outlook/events/?start_date=2025-12-23&end_date=2025-12-30"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["start_date"] == "2025-12-23"
        assert response.data["end_date"] == "2025-12-30"

    @patch(CLIENT_PATCH)
    def test_get_events_with_start_date_and_days(
        self, mock_client_class, authenticated_client
    ):
        """start_dateとdaysで予定一覧を取得できること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.return_value = []

        response = authenticated_client.get(
            "/outlook/events/?start_date=2025-12-25&days=3"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["start_date"] == "2025-12-25"
        assert response.data["end_date"] == "2025-12-27"

    def test_get_events_without_authentication_fails(self, api_client):
        """認証なしで予定一覧取得が失敗すること"""
        response = api_client.get("/outlook/events/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize(
        "query_string, expected_field",
        [
            pytest.param("?start_date=invalid", "start_date", id="invalid_date_format"),
            pytest.param("?days=0", "days", id="days_zero"),
            pytest.param("?days=-1", None, id="days_negative"),
        ],
    )
    def test_get_events_with_invalid_query_params(
        self, authenticated_client, query_string, expected_field
    ):
        """不正なクエリパラメータで 400 を返すこと"""
        response = authenticated_client.get(f"/outlook/events/{query_string}")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        if expected_field is not None:
            assert expected_field in response.data

    @patch(CLIENT_PATCH)
    def test_get_events_with_calendar_error(
        self, mock_client_class, authenticated_client
    ):
        """CalendarError 時に 400 を返すこと"""
        _set_client_method_error(
            mock_client_class,
            "get_calendar_events",
            CalendarError("Failed to fetch events"),
        )

        response = authenticated_client.get("/outlook/events/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Failed to fetch events"

    @pytest.mark.parametrize(
        "exception, status_code, expected_msg", COMMON_HANDLED_ERRORS
    )
    @patch(CLIENT_PATCH)
    def test_get_events_common_error_handling(
        self,
        mock_client_class,
        authenticated_client,
        exception,
        status_code,
        expected_msg,
    ):
        """共通エラーハンドリング（Configuration / Authentication / Network）"""
        _set_client_method_error(mock_client_class, "get_calendar_events", exception)

        response = authenticated_client.get("/outlook/events/")
        assert response.status_code == status_code
        assert expected_msg in response.data["error"]

    @patch(CLIENT_PATCH)
    def test_get_events_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に 500 を返すこと"""
        _set_client_method_error(
            mock_client_class, "get_calendar_events", Exception("Unexpected error")
        )

        response = authenticated_client.get("/outlook/events/")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "予定の取得中に問題が発生しました" in response.data["error"]

    @patch(CLIENT_PATCH)
    def test_get_events_all_day_event(self, mock_client_class, authenticated_client):
        """終日イベントが is_all_day=True で返されること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.return_value = [
            _sample_event(
                id="event-789",
                subject="休暇",
                start={"dateTime": "2025-12-25T00:00:00", "timeZone": "Asia/Tokyo"},
                end={"dateTime": "2025-12-26T00:00:00", "timeZone": "Asia/Tokyo"},
                location=None,
                isAllDay=True,
                bodyPreview="",
            )
        ]

        response = authenticated_client.get("/outlook/events/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["events"][0]["is_all_day"] is True
