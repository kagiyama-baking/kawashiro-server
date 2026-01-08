"""Tests for assistant views."""

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.fixtures.factories import UserFactory


@pytest.fixture
def api_client():
    """認証済みAPIクライアント."""
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def mock_assistant_service():
    """AssistantServiceのモック."""
    with patch("assistant.views.AssistantService") as mock:
        yield mock


@pytest.fixture
def mock_openai_client():
    """OpenAIClientのモック."""
    with patch("assistant.views.OpenAIClient") as mock:
        yield mock


@pytest.fixture
def mock_outlook_client():
    """OutlookGraphClientのモック."""
    with patch("assistant.views.OutlookGraphClient") as mock:
        yield mock


@pytest.fixture
def mock_weather_client():
    """JMAWeatherClientのモック."""
    with patch("assistant.views.JMAWeatherClient") as mock:
        yield mock


@pytest.mark.django_db
class TestGreetingView:
    """GreetingViewのテスト."""

    def test_greeting_success(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """挨拶生成が正常に動作する."""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = {
            "text": "おはようございます。",
            "events_count": 2,
            "weather_summary": "晴れ",
            "thinking": "予定と天気を確認します。",
            "tools_used": ["get_today_events", "get_weather_forecast"],
            "audio": None,
        }
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:greeting"),
            {"area_code": "130010", "greeting_type": "morning"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["text"] == "おはようございます。"
        assert response.data["events_count"] == 2
        assert response.data["thinking"] == "予定と天気を確認します。"
        assert "get_today_events" in response.data["tools_used"]

    def test_greeting_without_area_code(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """area_code未指定時、天気情報なしで挨拶生成."""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = {
            "text": "おはようございます。2件の予定があります。",
            "events_count": 2,
            "weather_summary": None,
            "thinking": "予定を確認します。",
            "tools_used": ["get_today_events"],
            "audio": None,
        }
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:greeting"),
            {"greeting_type": "morning"},  # area_code省略
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["text"] == "おはようございます。2件の予定があります。"
        assert response.data["weather_summary"] is None
        assert "get_weather_forecast" not in response.data["tools_used"]

    def test_greeting_with_audio(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """音声付き挨拶生成（data URI形式）."""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = {
            "text": "おはようございます。",
            "events_count": 1,
            "weather_summary": "晴れ",
            "thinking": None,
            "tools_used": ["get_today_events"],
            "audio": "data:audio/wav;base64,UklGRg==",
        }
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:greeting"),
            {"area_code": "130010", "include_audio": True},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["audio"].startswith("data:audio/wav;base64,")

    def test_greeting_unauthenticated(self):
        """認証なしでアクセス拒否."""
        client = APIClient()
        response = client.post(
            reverse("assistant:greeting"),
            {"area_code": "130010"},
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_greeting_openai_config_error(
        self,
        api_client,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """OpenAI設定エラー時に503を返す."""
        from assistant.exceptions import OpenAIConfigurationError

        mock_openai_client.side_effect = OpenAIConfigurationError("API key not set")

        response = api_client.post(
            reverse("assistant:greeting"),
            {"area_code": "130010"},
            format="json",
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_greeting_assistant_error(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """AssistantError時に502を返す."""
        from assistant.exceptions import OpenAIAPIError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = OpenAIAPIError("API Error")
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:greeting"),
            {"area_code": "130010"},
            format="json",
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.django_db
class TestChatView:
    """ChatViewのテスト."""

    def test_chat_success(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """チャットが正常に動作する."""
        mock_service = MagicMock()
        mock_service.chat.return_value = {
            "reply": "今日の予定は2件です。",
            "tools_used": ["get_today_events"],
            "audio": None,
        }
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:chat"),
            {"message": "今日の予定を教えて"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["reply"] == "今日の予定は2件です。"
        assert "get_today_events" in response.data["tools_used"]

    def test_chat_with_area_code(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """地域コード付きチャット."""
        mock_service = MagicMock()
        mock_service.chat.return_value = {
            "reply": "東京は晴れです。",
            "tools_used": ["get_weather_forecast"],
            "audio": None,
        }
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:chat"),
            {"message": "今日の天気は？", "area_code": "130010"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

    def test_chat_validation_error(self, api_client):
        """バリデーションエラー."""
        response = api_client.post(
            reverse("assistant:chat"),
            {},  # message missing
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_openai_config_error(
        self,
        api_client,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """OpenAI設定エラー時に503を返す."""
        from assistant.exceptions import OpenAIConfigurationError

        mock_openai_client.side_effect = OpenAIConfigurationError("API key not set")

        response = api_client.post(
            reverse("assistant:chat"),
            {"message": "今日の予定は？"},
            format="json",
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_chat_assistant_error(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """AssistantError時に502を返す."""
        from assistant.exceptions import OpenAIAPIError

        mock_service = MagicMock()
        mock_service.chat.side_effect = OpenAIAPIError("API Error")
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:chat"),
            {"message": "今日の予定は？"},
            format="json",
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.django_db
class TestGreetingAudioView:
    """GreetingAudioViewのテスト."""

    def test_greeting_audio_success(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """音声付き挨拶生成でWAVファイルを返す."""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = {
            "text": "おはようございます。",
            "events_count": 1,
            "weather_summary": "晴れ",
            "thinking": None,
            "tools_used": ["get_today_events"],
            "audio": "data:audio/wav;base64,UklGRg==",
        }
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:greeting-audio"),
            {"area_code": "130010"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert response["Content-Disposition"] == 'attachment; filename="greeting.wav"'

    def test_greeting_audio_no_audio_generated(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """音声生成に失敗した場合は404."""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = {
            "text": "おはようございます。",
            "events_count": 1,
            "weather_summary": "晴れ",
            "thinking": None,
            "tools_used": ["get_today_events"],
            "audio": None,
        }
        mock_assistant_service.return_value = mock_service

        response = api_client.post(
            reverse("assistant:greeting-audio"),
            {"area_code": "130010"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestDailySummaryView:
    """DailySummaryViewのテスト."""

    def test_daily_summary_success(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """日次サマリー取得が正常に動作する."""
        mock_service = MagicMock()
        mock_service.generate_daily_summary.return_value = {
            "summary": "本日は2件の予定があります。",
            "date": "2024-12-24",
            "audio": None,
        }
        mock_assistant_service.return_value = mock_service

        response = api_client.get(
            reverse("assistant:daily-summary"),
            {"area_code": "130010"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["summary"] == "本日は2件の予定があります。"
        assert response.data["date"] == "2024-12-24"

    def test_daily_summary_validation_error(self, api_client):
        """バリデーションエラー."""
        response = api_client.get(
            reverse("assistant:daily-summary"),
            {},  # area_code missing
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_daily_summary_openai_config_error(
        self,
        api_client,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """OpenAI設定エラー時に503を返す."""
        from assistant.exceptions import OpenAIConfigurationError

        mock_openai_client.side_effect = OpenAIConfigurationError("API key not set")

        response = api_client.get(
            reverse("assistant:daily-summary"),
            {"area_code": "130010"},
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_daily_summary_assistant_error(
        self,
        api_client,
        mock_assistant_service,
        mock_openai_client,
        mock_outlook_client,
        mock_weather_client,
    ):
        """AssistantError時に502を返す."""
        from assistant.exceptions import OpenAIAPIError

        mock_service = MagicMock()
        mock_service.generate_daily_summary.side_effect = OpenAIAPIError("API Error")
        mock_assistant_service.return_value = mock_service

        response = api_client.get(
            reverse("assistant:daily-summary"),
            {"area_code": "130010"},
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
