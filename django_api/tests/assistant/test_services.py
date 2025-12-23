"""Tests for AssistantService."""

import base64
from unittest.mock import MagicMock, Mock, patch

import pytest

from assistant.services import AssistantService


class TestAssistantServiceGenerateGreeting:
    """generate_greetingのテスト."""

    @pytest.fixture
    def mock_openai_client(self):
        """OpenAIクライアントのモック."""
        mock = MagicMock()
        mock.generate_text.return_value = (
            "おはようございます。今日は晴れで、最高気温は15度です。"
            "本日は朝会とランチミーティングの2件の予定があります。"
        )
        return mock

    @pytest.fixture
    def mock_outlook_client(self):
        """Outlookクライアントのモック."""
        mock = Mock()
        mock.get_calendar_events.return_value = [
            {
                "subject": "朝会",
                "start": {"dateTime": "2024-12-24T09:00:00"},
                "end": {"dateTime": "2024-12-24T09:30:00"},
            },
            {
                "subject": "ランチミーティング",
                "start": {"dateTime": "2024-12-24T12:00:00"},
                "end": {"dateTime": "2024-12-24T13:00:00"},
            },
        ]
        return mock

    @pytest.fixture
    def mock_weather_client(self):
        """天気クライアントのモック."""
        mock = Mock()
        mock.get_weather.return_value = {
            "area_name": "東京都 東京地方",
            "weather": "晴れ",
            "temp_min": 5,
            "temp_max": 15,
        }
        return mock

    @pytest.fixture
    def service(self, mock_openai_client, mock_outlook_client, mock_weather_client):
        """AssistantServiceインスタンス."""
        return AssistantService(
            openai_client=mock_openai_client,
            outlook_client=mock_outlook_client,
            weather_client=mock_weather_client,
            tts_service_url="http://localhost:5000",
        )

    def test_generate_greeting_morning(self, service, mock_openai_client):
        """朝の挨拶生成."""
        result = service.generate_greeting(
            area_code="130010", greeting_type="morning", include_audio=False
        )

        assert "text" in result
        assert result["text"] is not None
        assert "events_count" in result
        assert result["events_count"] == 2
        assert "weather_summary" in result
        mock_openai_client.generate_text.assert_called_once()

    def test_generate_greeting_with_greeting_types(self, service, mock_openai_client):
        """異なる挨拶タイプで生成できる."""
        for greeting_type in ["morning", "afternoon", "evening"]:
            mock_openai_client.reset_mock()
            result = service.generate_greeting(
                area_code="130010",
                greeting_type=greeting_type,
                include_audio=False,
            )
            assert result["text"] is not None

    @patch("assistant.services.requests.post")
    def test_generate_greeting_with_audio(self, mock_post, service, mock_openai_client):
        """音声付きの挨拶生成."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        result = service.generate_greeting(
            area_code="130010", greeting_type="morning", include_audio=True
        )

        assert "audio" in result
        assert result["audio"] is not None
        # Base64エンコードされている
        decoded = base64.b64decode(result["audio"])
        assert decoded == b"fake audio data"

    def test_generate_greeting_without_audio(self, service):
        """音声なしの挨拶生成."""
        result = service.generate_greeting(
            area_code="130010", greeting_type="morning", include_audio=False
        )

        assert result.get("audio") is None


class TestAssistantServiceChat:
    """chatのテスト."""

    @pytest.fixture
    def mock_openai_client(self):
        """OpenAIクライアントのモック."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def mock_outlook_client(self):
        """Outlookクライアントのモック."""
        mock = Mock()
        mock.get_calendar_events.return_value = [
            {
                "subject": "朝会",
                "start": {"dateTime": "2024-12-24T09:00:00"},
            },
        ]
        return mock

    @pytest.fixture
    def mock_weather_client(self):
        """天気クライアントのモック."""
        mock = Mock()
        mock.get_weather.return_value = {
            "area_name": "東京都 東京地方",
            "weather": "晴れ",
        }
        return mock

    @pytest.fixture
    def service(self, mock_openai_client, mock_outlook_client, mock_weather_client):
        """AssistantServiceインスタンス."""
        return AssistantService(
            openai_client=mock_openai_client,
            outlook_client=mock_outlook_client,
            weather_client=mock_weather_client,
            tts_service_url="http://localhost:5000",
        )

    def test_chat_without_tool_calls(self, service, mock_openai_client):
        """ツール呼び出しなしのチャット."""
        mock_message = Mock()
        mock_message.content = "こんにちは！何かお手伝いできることはありますか？"
        mock_message.tool_calls = None
        mock_openai_client.chat_completion.return_value = mock_message

        result = service.chat(message="こんにちは", include_audio=False)

        assert result["reply"] == "こんにちは！何かお手伝いできることはありますか？"
        assert result["tools_used"] == []

    def test_chat_with_tool_calls(self, service, mock_openai_client):
        """ツール呼び出しありのチャット."""
        # 最初の応答：ツール呼び出し
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "get_today_events"
        mock_tool_call.function.arguments = "{}"

        mock_first_message = Mock()
        mock_first_message.content = None
        mock_first_message.tool_calls = [mock_tool_call]

        # 2回目の応答：最終回答
        mock_final_message = Mock()
        mock_final_message.content = "今日の予定は朝会が1件あります。"
        mock_final_message.tool_calls = None

        mock_openai_client.chat_completion.side_effect = [
            mock_first_message,
            mock_final_message,
        ]

        result = service.chat(message="今日の予定を教えて", include_audio=False)

        assert result["reply"] == "今日の予定は朝会が1件あります。"
        assert "get_today_events" in result["tools_used"]

    def test_chat_with_weather_tool(
        self, service, mock_openai_client, mock_weather_client
    ):
        """天気ツールを使ったチャット."""
        mock_tool_call = Mock()
        mock_tool_call.id = "call_456"
        mock_tool_call.function.name = "get_weather_forecast"
        mock_tool_call.function.arguments = '{"area_code": "130010"}'

        mock_first_message = Mock()
        mock_first_message.content = None
        mock_first_message.tool_calls = [mock_tool_call]

        mock_final_message = Mock()
        mock_final_message.content = "東京は今日晴れです。"
        mock_final_message.tool_calls = None

        mock_openai_client.chat_completion.side_effect = [
            mock_first_message,
            mock_final_message,
        ]

        result = service.chat(
            message="今日の天気は？",
            area_code="130010",
            include_audio=False,
        )

        assert result["reply"] == "東京は今日晴れです。"
        assert "get_weather_forecast" in result["tools_used"]


class TestAssistantServiceDailySummary:
    """generate_daily_summaryのテスト."""

    @pytest.fixture
    def mock_openai_client(self):
        """OpenAIクライアントのモック."""
        mock = MagicMock()
        mock.generate_text.return_value = (
            "本日は2件の予定があります。天気は晴れで過ごしやすい一日です。"
        )
        return mock

    @pytest.fixture
    def mock_outlook_client(self):
        """Outlookクライアントのモック."""
        mock = Mock()
        mock.get_calendar_events.return_value = [
            {"subject": "朝会", "start": {"dateTime": "2024-12-24T09:00:00"}},
            {"subject": "会議", "start": {"dateTime": "2024-12-24T14:00:00"}},
        ]
        return mock

    @pytest.fixture
    def mock_weather_client(self):
        """天気クライアントのモック."""
        mock = Mock()
        mock.get_weather.return_value = {
            "area_name": "東京都 東京地方",
            "weather": "晴れ",
            "temp_max": 15,
        }
        return mock

    @pytest.fixture
    def service(self, mock_openai_client, mock_outlook_client, mock_weather_client):
        """AssistantServiceインスタンス."""
        return AssistantService(
            openai_client=mock_openai_client,
            outlook_client=mock_outlook_client,
            weather_client=mock_weather_client,
            tts_service_url="http://localhost:5000",
        )

    def test_generate_daily_summary(self, service):
        """日次サマリー生成."""
        result = service.generate_daily_summary(area_code="130010", include_audio=False)

        assert "summary" in result
        assert result["summary"] is not None
        assert "date" in result

    def test_generate_daily_summary_with_audio(self, service):
        """音声付き日次サマリー生成."""
        with patch("assistant.services.requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b"audio data"
            mock_post.return_value = mock_response

            result = service.generate_daily_summary(
                area_code="130010", include_audio=True
            )

            assert result.get("audio") is not None
