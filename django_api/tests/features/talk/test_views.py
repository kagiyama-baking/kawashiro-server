"""Tests for talk views."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from features.talk.models import TalkConfig
from integrations.langfuse.models import LangfusePromptRef


@pytest.fixture
def prompt_refs(db):
    sys_ref = LangfusePromptRef.objects.create(
        name="talk-view-system",
        langfuse_prompt_name="talk-view-system",
        fallback_text="system fallback",
    )
    user_ref = LangfusePromptRef.objects.create(
        name="talk-view-user",
        langfuse_prompt_name="talk-view-user",
        fallback_text="user fallback",
    )
    return sys_ref, user_ref


def _refs(prompt_refs):
    return {
        "system_prompt_ref": prompt_refs[0],
        "user_prompt_ref": prompt_refs[1],
    }


@pytest.mark.django_db
class TestTodayInfoView:
    """TodayInfoViewのテスト"""

    @pytest.fixture
    def url(self):
        return reverse("talk:datetime")

    def test_today_info_unauthorized(self, api_client, url):
        """未認証の場合は401エラー."""
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("features.talk.views.HolidayClient")
    @patch("features.talk.views.datetime")
    def test_today_info_success_weekday(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """平日の日時情報が取得できる."""
        mock_now = datetime(2025, 1, 14, 9, 30, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.return_value = None
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["date"] == "2025-01-14"
        assert response.data["time"] == "09:30:00"
        assert response.data["day_of_week"] == "Tuesday"
        assert response.data["day_of_week_ja"] == "火曜日"
        assert response.data["holiday_name"] is None

    @patch("features.talk.views.HolidayClient")
    @patch("features.talk.views.datetime")
    def test_today_info_success_holiday(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """祝日の日時情報が取得できる."""
        mock_now = datetime(2025, 1, 1, 8, 0, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.return_value = "元日"
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["holiday_name"] == "元日"

    @patch("features.talk.views.HolidayClient")
    @patch("features.talk.views.datetime")
    def test_today_info_holiday_api_network_error(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """祝日APIネットワークエラー時は502エラー."""
        from features.talk.exceptions import HolidayNetworkError

        mock_now = datetime(2025, 1, 14, 9, 30, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.side_effect = HolidayNetworkError("Network error")
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("features.talk.views.HolidayClient")
    @patch("features.talk.views.datetime")
    def test_today_info_holiday_api_timeout(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """祝日APIタイムアウト時は504エラー."""
        from features.talk.exceptions import HolidayTimeoutError

        mock_now = datetime(2025, 1, 14, 9, 30, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.side_effect = HolidayTimeoutError("Timeout")
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    @patch("features.talk.views.HolidayClient")
    @patch("features.talk.views.datetime")
    def test_today_info_unexpected_error(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """予期しないエラー時は500エラー."""
        mock_now = datetime(2025, 1, 14, 9, 30, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.side_effect = RuntimeError("Unexpected")
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.django_db
class TestTalkSynthesizeView:
    """TalkSynthesizeViewのテスト"""

    @pytest.fixture
    def url(self):
        return reverse("talk:synthesize")

    @pytest.fixture
    def greeting_config(self, prompt_refs):
        return TalkConfig.objects.create(
            name="test",
            display_name="テスト設定",
            use_weather=False,
            use_events=False,
            use_datetime=True,
            tts_enabled=False,
            **_refs(prompt_refs),
        )

    @pytest.fixture
    def greeting_config_with_weather(self, prompt_refs):
        return TalkConfig.objects.create(
            name="weather_test",
            display_name="天気テスト設定",
            use_weather=True,
            use_events=False,
            use_datetime=True,
            area_code="130010",
            tts_enabled=False,
            **_refs(prompt_refs),
        )

    @pytest.fixture
    def greeting_config_with_tts(self, prompt_refs):
        return TalkConfig.objects.create(
            name="tts_test",
            display_name="TTSテスト設定",
            use_weather=False,
            use_events=False,
            use_datetime=True,
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_speed=1.2,
            **_refs(prompt_refs),
        )

    @pytest.fixture
    def request_data(self, greeting_config):
        return {"config_name": greeting_config.name}

    @pytest.fixture
    def mock_greeting_response(self):
        return {
            "greeting_text": "おはようございます、先輩。今日も頑張りましょう。",
        }

    @pytest.fixture
    def mock_greeting_response_with_audio(self):
        return {
            "greeting_text": "おはようございます、先輩。今日も頑張りましょう。",
            "audio_data": b"fake_wav_data",
            "audio_content_type": "audio/wav",
            "audio_format": "wav",
        }

    def test_greeting_unauthorized(self, api_client, url, greeting_config):
        """未認証の場合は401エラー."""
        response = api_client.post(
            url,
            {"config_name": greeting_config.name},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_greeting_config_not_found(self, authenticated_client, url):
        """設定が存在しない場合は404エラー."""
        response = authenticated_client.post(
            url,
            {"config_name": "nonexistent"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    def test_greeting_missing_config_name(self, authenticated_client, url):
        """config_name が欠落している場合は400エラー."""
        response = authenticated_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("features.talk.views.TalkService")
    def test_greeting_success(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
        mock_greeting_response,
    ):
        """正常系: 挨拶がJSONで取得できる."""
        mock_service = MagicMock()
        mock_service.synthesize.return_value = mock_greeting_response
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["greeting_text"] == mock_greeting_response["greeting_text"]

        mock_service.synthesize.assert_called_once()
        call_kwargs = mock_service.synthesize.call_args.kwargs
        assert call_kwargs["config"].name == greeting_config.name
        assert "user_prompt" not in call_kwargs

    @patch("features.talk.views.TalkService")
    def test_greeting_with_tts_enabled(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
        mock_greeting_response_with_audio,
    ):
        """TTS有効時: 音声データがWAVで返される."""
        mock_service = MagicMock()
        mock_service.synthesize.return_value = mock_greeting_response_with_audio
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(
            url,
            {"config_name": greeting_config_with_tts.name},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/json"
        assert response.data["audio_data"] is not None
        assert response.data["audio_format"] == "wav"

    @patch("features.talk.views.TalkService")
    def test_greeting_weather_api_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_weather,
    ):
        """天気予報API失敗時に502エラー."""
        from integrations.weather.exceptions import WeatherNetworkError

        mock_service = MagicMock()
        mock_service.synthesize.side_effect = WeatherNetworkError("Network error")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(
            url,
            {"config_name": greeting_config_with_weather.name},
            format="json",
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("features.talk.views.TalkService")
    def test_greeting_openai_timeout(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """LLM APIタイムアウト時に504エラー."""
        from integrations.llm.exceptions import LLMTimeoutError

        mock_service = MagicMock()
        mock_service.synthesize.side_effect = LLMTimeoutError("Timeout")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    @patch("features.talk.views.TalkService")
    def test_greeting_area_not_found(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_weather,
    ):
        """予報区コードが見つからない場合は404エラー."""
        from integrations.weather.exceptions import WeatherAreaNotFoundError

        mock_service = MagicMock()
        mock_service.synthesize.side_effect = WeatherAreaNotFoundError("not found")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(
            url,
            {"config_name": greeting_config_with_weather.name},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("features.talk.views.TalkService")
    def test_greeting_with_tts_long_text_not_truncated(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
    ):
        """TTS有効時: 長いテキストが切り詰められない."""
        long_text = "あ" * 500
        mock_service = MagicMock()
        mock_service.synthesize.return_value = {
            "greeting_text": long_text,
            "audio_data": b"fake_wav_data",
            "audio_content_type": "audio/wav",
            "audio_format": "wav",
        }
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(
            url,
            {"config_name": greeting_config_with_tts.name},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["greeting_text"]) == 500

    @patch("features.talk.views.TalkService")
    def test_greeting_weather_timeout(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_weather,
    ):
        """天気APIタイムアウト時に504エラー."""
        from integrations.weather.exceptions import WeatherTimeoutError

        mock_service = MagicMock()
        mock_service.synthesize.side_effect = WeatherTimeoutError("Timeout")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(
            url,
            {"config_name": greeting_config_with_weather.name},
            format="json",
        )
        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    @patch("features.talk.views.TalkService")
    def test_greeting_openai_api_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """LLM APIエラー時に502エラー."""
        from integrations.llm.exceptions import LLMClientError

        mock_service = MagicMock()
        mock_service.synthesize.side_effect = LLMClientError("API error")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("features.talk.views.TalkService")
    def test_greeting_tts_network_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """TTSネットワークエラー時に502エラー."""
        from integrations.tts.exceptions import TTSNetworkError

        mock_service = MagicMock()
        mock_service.synthesize.side_effect = TTSNetworkError("Connection failed")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("features.talk.views.TalkService")
    def test_greeting_configuration_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """サービス設定エラー時に503エラー."""
        from integrations.msgraph.exceptions import ConfigurationError

        mock_service = MagicMock()
        mock_service.synthesize.side_effect = ConfigurationError("Config missing")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("features.talk.views.TalkService")
    def test_greeting_authentication_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """外部サービス認証エラー時に502エラー."""
        from integrations.msgraph.exceptions import AuthenticationError

        mock_service = MagicMock()
        mock_service.synthesize.side_effect = AuthenticationError("Auth failed")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("features.talk.views.TalkService")
    def test_greeting_unexpected_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """予期しないエラー時に500エラー."""
        mock_service = MagicMock()
        mock_service.synthesize.side_effect = RuntimeError("Unexpected")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.django_db
class TestConfigsListView:
    """ConfigsListViewのテスト"""

    @pytest.fixture
    def url(self):
        return reverse("talk:configs")

    def test_configs_list_unauthorized(self, api_client, url):
        """未認証の場合は401エラー."""
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_configs_list_empty(self, authenticated_client, url):
        """設定がない場合は空リスト."""
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["configs"] == []

    def test_configs_list_with_data(self, authenticated_client, url, prompt_refs):
        """設定がある場合はリストで返す."""
        TalkConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            use_weather=True,
            use_events=True,
            use_datetime=True,
            area_code="130010",
            tts_enabled=True,
            **_refs(prompt_refs),
        )
        TalkConfig.objects.create(
            name="evening",
            display_name="夕方のあいさつ",
            use_weather=False,
            use_events=False,
            use_datetime=True,
            tts_enabled=False,
            **_refs(prompt_refs),
        )

        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        configs = response.data["configs"]
        assert len(configs) == 2

        names = {c["name"] for c in configs}
        assert names == {"morning", "evening"}

        morning = next(c for c in configs if c["name"] == "morning")
        assert morning["display_name"] == "朝のあいさつ"
        assert morning["tts_enabled"] is True
        assert morning["use_weather"] is True
