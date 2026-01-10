"""Outlookアプリのビューテスト"""

from unittest.mock import Mock, patch

import pytest
from rest_framework import status


@pytest.mark.api
class TestOutlookEventsView:
    """OutlookEventsViewのテストクラス"""

    @patch("outlook.views.OutlookMSGraphClient")
    def test_get_events_success_default_params(
        self, mock_client_class, authenticated_client
    ):
        """デフォルトパラメータで予定一覧の取得が成功すること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.return_value = [
            {
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
        ]

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_200_OK
        assert "start_date" in response.data
        assert "end_date" in response.data
        assert "count" in response.data
        assert "events" in response.data
        assert response.data["count"] == 1
        assert response.data["events"][0]["subject"] == "チーム定例"

    @patch("outlook.views.OutlookMSGraphClient")
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

        # クライアントメソッドが呼ばれたことを確認
        mock_client.get_calendar_events.assert_called_once()

    @patch("outlook.views.OutlookMSGraphClient")
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

    @patch("outlook.views.OutlookMSGraphClient")
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
        # end_dateはstart_date + days - 1
        assert response.data["end_date"] == "2025-12-27"

    def test_get_events_without_authentication_fails(self, api_client):
        """認証なしで予定一覧取得が失敗すること"""
        response = api_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_events_with_invalid_date_format(self, authenticated_client):
        """不正な日付形式でエラーになること"""
        response = authenticated_client.get("/outlook/events/?start_date=invalid")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "start_date" in response.data

    def test_get_events_with_invalid_days(self, authenticated_client):
        """不正なdays値でエラーになること"""
        response = authenticated_client.get("/outlook/events/?days=0")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "days" in response.data

    def test_get_events_with_negative_days(self, authenticated_client):
        """負のdays値でエラーになること"""
        response = authenticated_client.get("/outlook/events/?days=-1")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("outlook.views.OutlookMSGraphClient")
    def test_get_events_with_configuration_error(
        self, mock_client_class, authenticated_client
    ):
        """設定エラー時に適切なエラーレスポンスを返すこと"""
        from msgraph_config.exceptions import ConfigurationError

        mock_client_class.side_effect = ConfigurationError("Missing configuration")

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "サービスの設定に問題があります" in response.data["error"]

    @patch("outlook.views.OutlookMSGraphClient")
    def test_get_events_with_authentication_error(
        self, mock_client_class, authenticated_client
    ):
        """認証エラー時に適切なエラーレスポンスを返すこと"""
        from msgraph_config.exceptions import AuthenticationError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.side_effect = AuthenticationError(
            "Token expired"
        )

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Outlookへの認証に失敗しました" in response.data["error"]

    @patch("outlook.views.OutlookMSGraphClient")
    def test_get_events_with_calendar_error(
        self, mock_client_class, authenticated_client
    ):
        """カレンダー取得エラー時に適切なエラーレスポンスを返すこと"""
        from outlook.exceptions import CalendarError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.side_effect = CalendarError(
            "Failed to fetch events"
        )

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Failed to fetch events"

    @patch("outlook.views.OutlookMSGraphClient")
    def test_get_events_with_network_error(
        self, mock_client_class, authenticated_client
    ):
        """ネットワークエラー時に適切なエラーレスポンスを返すこと"""
        from msgraph_config.exceptions import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.side_effect = NetworkError("Connection timeout")

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "Outlookへの接続に失敗しました" in response.data["error"]

    @patch("outlook.views.OutlookMSGraphClient")
    def test_get_events_with_unexpected_error(
        self, mock_client_class, authenticated_client
    ):
        """予期しないエラー時に適切なエラーレスポンスを返すこと"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.side_effect = Exception("Unexpected error")

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "予定の取得中に問題が発生しました" in response.data["error"]

    @patch("outlook.views.OutlookMSGraphClient")
    def test_get_events_response_format(self, mock_client_class, authenticated_client):
        """レスポンスが正しい形式であること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.return_value = [
            {
                "id": "event-456",
                "subject": "1on1ミーティング",
                "start": {"dateTime": "2025-12-23T14:00:00", "timeZone": "Asia/Tokyo"},
                "end": {"dateTime": "2025-12-23T14:30:00", "timeZone": "Asia/Tokyo"},
                "location": {"displayName": "オンライン"},
                "isAllDay": False,
                "organizer": {"emailAddress": {"address": "manager@example.com"}},
                "webLink": "https://outlook.office365.com/event/456",
                "bodyPreview": "定期1on1",
            }
        ]

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_200_OK
        event = response.data["events"][0]

        # 期待されるフィールドがあることを確認
        assert "id" in event
        assert "subject" in event
        assert "start" in event
        assert "end" in event
        assert "location" in event
        assert "is_all_day" in event
        assert "organizer" in event
        assert "web_link" in event
        assert "body_preview" in event

    @patch("outlook.views.OutlookMSGraphClient")
    def test_get_events_all_day_event(self, mock_client_class, authenticated_client):
        """終日イベントが正しく処理されること"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_calendar_events.return_value = [
            {
                "id": "event-789",
                "subject": "休暇",
                "start": {"dateTime": "2025-12-25T00:00:00", "timeZone": "Asia/Tokyo"},
                "end": {"dateTime": "2025-12-26T00:00:00", "timeZone": "Asia/Tokyo"},
                "location": None,
                "isAllDay": True,
                "organizer": {"emailAddress": {"address": "user@example.com"}},
                "webLink": "https://outlook.office365.com/event/789",
                "bodyPreview": "",
            }
        ]

        response = authenticated_client.get("/outlook/events/")

        assert response.status_code == status.HTTP_200_OK
        event = response.data["events"][0]
        assert event["is_all_day"] is True
