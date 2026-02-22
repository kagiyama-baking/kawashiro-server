"""Tests for greeting views."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from greeting.models import GreetingConfig


@pytest.mark.django_db
class TestTodayInfoView:
    """TodayInfoViewのテスト"""

    @pytest.fixture
    def url(self):
        """エンドポイントURL"""
        return reverse("greeting:today")

    def test_today_info_unauthorized(self, api_client, url):
        """未認証の場合は401エラー"""
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("greeting.views.HolidayClient")
    @patch("greeting.views.datetime")
    def test_today_info_success_weekday(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """正常系: 平日の場合"""
        # 2025年1月14日 火曜日 09:30:00
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

    @patch("greeting.views.HolidayClient")
    @patch("greeting.views.datetime")
    def test_today_info_success_holiday(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """正常系: 祝日の場合"""
        # 2025年1月1日 水曜日 08:00:00 元日
        mock_now = datetime(2025, 1, 1, 8, 0, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.return_value = "元日"
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["date"] == "2025-01-01"
        assert response.data["time"] == "08:00:00"
        assert response.data["day_of_week"] == "Wednesday"
        assert response.data["day_of_week_ja"] == "水曜日"
        assert response.data["holiday_name"] == "元日"

    @patch("greeting.views.HolidayClient")
    @patch("greeting.views.datetime")
    def test_today_info_holiday_api_network_error(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """祝日APIネットワークエラー時は502エラー"""
        from greeting.exceptions import HolidayNetworkError

        mock_now = datetime(2025, 1, 14, 9, 30, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.side_effect = HolidayNetworkError("Network error")
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("greeting.views.HolidayClient")
    @patch("greeting.views.datetime")
    def test_today_info_holiday_api_timeout(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """祝日APIタイムアウト時は504エラー"""
        from greeting.exceptions import HolidayTimeoutError

        mock_now = datetime(2025, 1, 14, 9, 30, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.side_effect = HolidayTimeoutError("Timeout")
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "error" in response.data

    @patch("greeting.views.HolidayClient")
    @patch("greeting.views.datetime")
    def test_today_info_unexpected_error(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """予期しないエラー時は500エラー"""
        mock_now = datetime(2025, 1, 14, 9, 30, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.side_effect = RuntimeError("Unexpected")
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "error" in response.data


@pytest.mark.django_db
class TestGreetingView:
    """GreetingViewのテスト"""

    @pytest.fixture
    def url(self):
        """エンドポイントURL"""
        return reverse("greeting:generate")

    @pytest.fixture
    def greeting_config(self):
        """挨拶設定（日時のみ使用）"""
        return GreetingConfig.objects.create(
            name="test",
            display_name="テスト設定",
            use_weather=False,
            use_events=False,
            use_datetime=True,
            system_prompt="テスト用システムプロンプト",
            tts_enabled=False,
        )

    @pytest.fixture
    def greeting_config_with_weather(self):
        """挨拶設定（天気使用）"""
        return GreetingConfig.objects.create(
            name="weather_test",
            display_name="天気テスト設定",
            use_weather=True,
            use_events=False,
            use_datetime=True,
            area_code="130010",
            system_prompt="テスト用システムプロンプト",
            tts_enabled=False,
        )

    @pytest.fixture
    def greeting_config_with_tts(self):
        """TTS有効の挨拶設定"""
        return GreetingConfig.objects.create(
            name="tts_test",
            display_name="TTSテスト設定",
            use_weather=False,
            use_events=False,
            use_datetime=True,
            system_prompt="テスト用システムプロンプト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_speed=1.2,
        )

    @pytest.fixture
    def request_data(self, greeting_config):
        """リクエストデータ"""
        return {
            "config_name": greeting_config.name,
            "user_prompt": "今日は{{datetime}}です。挨拶してください。",
        }

    @pytest.fixture
    def mock_greeting_response(self):
        """サービスのモックレスポンス（テキストのみ）"""
        return {
            "greeting_text": "おはようございます、先輩。今日も頑張りましょう。",
        }

    @pytest.fixture
    def mock_greeting_response_with_audio(self):
        """サービスのモックレスポンス（音声あり）"""
        return {
            "greeting_text": "おはようございます、先輩。今日も頑張りましょう。",
            "audio_data": b"fake_wav_data",
            "audio_content_type": "audio/wav",
            "audio_format": "wav",
        }

    def test_greeting_unauthorized(self, api_client, url, greeting_config):
        """未認証の場合は401エラー"""
        response = api_client.post(
            url,
            {"config_name": greeting_config.name, "user_prompt": "test"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_greeting_config_not_found(self, authenticated_client, url):
        """設定が存在しない場合は404エラー"""
        response = authenticated_client.post(
            url,
            {"config_name": "nonexistent", "user_prompt": "test"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    def test_greeting_missing_config_name(
        self, authenticated_client, url, greeting_config
    ):
        """config_nameが欠落している場合は400エラー"""
        response = authenticated_client.post(
            url,
            {"user_prompt": "test"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_greeting_missing_user_prompt(
        self, authenticated_client, url, greeting_config
    ):
        """user_promptが欠落している場合は400エラー"""
        response = authenticated_client.post(
            url,
            {"config_name": greeting_config.name},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("greeting.views.GreetingService")
    def test_greeting_success(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
        mock_greeting_response,
    ):
        """正常系: 挨拶がJSONで取得できる"""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = mock_greeting_response
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "greeting_text" in response.data
        assert response.data["greeting_text"] == mock_greeting_response["greeting_text"]

        # サービスが正しい引数で呼ばれたことを確認
        mock_service.generate_greeting.assert_called_once()
        call_kwargs = mock_service.generate_greeting.call_args.kwargs
        assert call_kwargs["config"].name == greeting_config.name
        assert call_kwargs["user_prompt"] == request_data["user_prompt"]

    @patch("greeting.views.GreetingService")
    def test_greeting_with_tts_enabled(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
        mock_greeting_response_with_audio,
    ):
        """TTS有効時: 音声データがWAVで返される"""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = mock_greeting_response_with_audio
        mock_service_class.return_value = mock_service

        request_data = {
            "config_name": greeting_config_with_tts.name,
            "user_prompt": "test",
        }

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert "X-Greeting-Text" in response
        assert "greeting.wav" in response["Content-Disposition"]

    @patch("greeting.views.GreetingService")
    def test_greeting_weather_api_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_weather,
    ):
        """天気予報API失敗時に502エラー"""
        from weather.exceptions import JMANetworkError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMANetworkError("Network error")
        mock_service_class.return_value = mock_service

        request_data = {
            "config_name": greeting_config_with_weather.name,
            "user_prompt": "test",
        }

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("greeting.views.GreetingService")
    def test_greeting_openai_timeout(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """OpenAI APIタイムアウト時に504エラー"""
        from llm_client.exceptions import OpenAITimeoutError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = OpenAITimeoutError("Timeout")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "error" in response.data

    @patch("greeting.views.GreetingService")
    def test_greeting_area_not_found(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_weather,
    ):
        """予報区コードが見つからない場合は404エラー"""
        from weather.exceptions import JMAAreaNotFoundError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMAAreaNotFoundError(
            "Area not found"
        )
        mock_service_class.return_value = mock_service

        request_data = {
            "config_name": greeting_config_with_weather.name,
            "user_prompt": "test",
        }

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("greeting.views.GreetingService")
    def test_greeting_header_sanitizes_control_chars(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
    ):
        """X-Greeting-Textヘッダーから制御文字が除去される"""
        from email.header import decode_header

        mock_service = MagicMock()
        # 制御文字を含むテキスト
        mock_service.generate_greeting.return_value = {
            "greeting_text": "おはよう\r\nございます\x00先輩",
            "audio_data": b"fake_wav_data",
            "audio_content_type": "audio/wav",
            "audio_format": "wav",
        }
        mock_service_class.return_value = mock_service

        request_data = {
            "config_name": greeting_config_with_tts.name,
            "user_prompt": "test",
        }

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_200_OK
        raw_header = response["X-Greeting-Text"]

        # MIMEエンコードされている場合はデコード
        decoded_parts = decode_header(raw_header)
        header_text = "".join(
            part.decode(encoding or "utf-8") if isinstance(part, bytes) else part
            for part, encoding in decoded_parts
        )

        # 制御文字が除去されていること
        assert "\r" not in header_text
        assert "\n" not in header_text
        assert "\x00" not in header_text
        # 元のテキストの意味は保持
        assert "おはよう" in header_text
        assert "先輩" in header_text

    @patch("greeting.views.GreetingService")
    def test_greeting_jma_timeout(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_weather,
    ):
        """天気APIタイムアウト時に504エラー"""
        from weather.exceptions import JMATimeoutError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMATimeoutError("Timeout")
        mock_service_class.return_value = mock_service

        request_data = {
            "config_name": greeting_config_with_weather.name,
            "user_prompt": "test",
        }

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "error" in response.data

    @patch("greeting.views.GreetingService")
    def test_greeting_openai_api_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """OpenAI APIエラー時に502エラー"""
        from llm_client.exceptions import OpenAIAPIError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = OpenAIAPIError("API error")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("greeting.views.GreetingService")
    def test_greeting_tts_network_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """TTSネットワークエラー時に502エラー"""
        from tts.exceptions import TTSNetworkError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = TTSNetworkError(
            "Connection failed"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("greeting.views.GreetingService")
    def test_greeting_configuration_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """サービス設定エラー時に503エラー"""
        from msgraph_config.exceptions import ConfigurationError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = ConfigurationError(
            "Config missing"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "error" in response.data

    @patch("greeting.views.GreetingService")
    def test_greeting_authentication_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """外部サービス認証エラー時に502エラー"""
        from msgraph_config.exceptions import AuthenticationError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = AuthenticationError("Auth failed")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "error" in response.data

    @patch("greeting.views.GreetingService")
    def test_greeting_unexpected_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """予期しないエラー時に500エラー"""
        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = RuntimeError("Unexpected")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "error" in response.data
