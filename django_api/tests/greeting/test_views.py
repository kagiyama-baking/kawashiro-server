"""Tests for greeting views."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from greeting.models import (
    EveningGreetingConfig,
    MorningGreetingConfig,
    WelcomeHomeGreetingConfig,
)


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
    def test_today_info_success_saturday(
        self, mock_datetime, mock_holiday_client_class, authenticated_client, url
    ):
        """正常系: 土曜日の場合"""
        # 2025年1月11日 土曜日 10:00:00
        mock_now = datetime(2025, 1, 11, 10, 0, 0)
        mock_datetime.now.return_value = mock_now

        mock_client = MagicMock()
        mock_client.get_holiday_name.return_value = None
        mock_holiday_client_class.return_value = mock_client

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["date"] == "2025-01-11"
        assert response.data["time"] == "10:00:00"
        assert response.data["day_of_week"] == "Saturday"
        assert response.data["day_of_week_ja"] == "土曜日"
        assert response.data["holiday_name"] is None

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


@pytest.mark.django_db
class TestMorningGreetingView:
    """MorningGreetingViewのテスト"""

    @pytest.fixture
    def url(self):
        """エンドポイントURL"""
        return reverse("greeting:morning")

    @pytest.fixture
    def greeting_config(self):
        """朝のあいさつ設定"""
        return MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="テスト用システムプロンプト",
            tts_enabled=False,
        )

    @pytest.fixture
    def greeting_config_with_tts(self):
        """TTS有効の朝のあいさつ設定"""
        return MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="テスト用システムプロンプト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_speed=1.2,
        )

    @pytest.fixture
    def request_data(self):
        """リクエストデータ"""
        return {"user_prompt": "テスト用ユーザープロンプト"}

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
            "audio_data": b"RIFF....WAVEfmt ",
        }

    def test_morning_greeting_unauthorized(
        self, api_client, url, greeting_config, request_data
    ):
        """未認証の場合は401エラー"""
        response = api_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_morning_greeting_config_not_found(
        self, authenticated_client, url, request_data
    ):
        """設定が存在しない場合は404エラー"""
        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    def test_morning_greeting_missing_user_prompt(
        self, authenticated_client, url, greeting_config
    ):
        """user_promptが欠落している場合は400エラー"""
        response = authenticated_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_success(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
        mock_greeting_response,
    ):
        """正常系: 挨拶がJSONで取得できる（TTS無効時）"""
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
        assert call_kwargs["area_code"] == "130010"
        assert call_kwargs["system_prompt"] == "テスト用システムプロンプト"
        assert call_kwargs["user_prompt"] == "テスト用ユーザープロンプト"
        assert call_kwargs["tts_options"] is None

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_with_tts_enabled(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
        request_data,
        mock_greeting_response_with_audio,
    ):
        """TTS有効時: 音声データがWAVで返される"""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = mock_greeting_response_with_audio
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert "X-Greeting-Text" in response

        # TTSオプションが正しく渡されることを確認
        mock_service.generate_greeting.assert_called_once()
        call_kwargs = mock_service.generate_greeting.call_args.kwargs
        assert call_kwargs["tts_options"] is not None
        assert call_kwargs["tts_options"]["model"] == "test_model"
        assert call_kwargs["tts_options"]["style"] == "Happy"
        assert call_kwargs["tts_options"]["speed"] == 1.2

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_weather_api_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """天気予報API失敗時に502エラー"""
        from weather.exceptions import JMANetworkError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMANetworkError("Network error")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_openai_timeout(
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

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_area_not_found(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """予報区コードが見つからない場合は404エラー"""
        from weather.exceptions import JMAAreaNotFoundError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMAAreaNotFoundError(
            "Area not found"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_header_sanitizes_control_chars(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
        request_data,
    ):
        """X-Greeting-Textヘッダーから制御文字が除去される"""
        from email.header import decode_header

        mock_service = MagicMock()
        # 制御文字を含むテキスト
        mock_service.generate_greeting.return_value = {
            "greeting_text": "おはよう\r\nございます\x00先輩",
            "audio_data": b"RIFF....WAVEfmt ",
        }
        mock_service_class.return_value = mock_service

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

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_area_not_found_generic_message(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """予報区コードエラー時は汎用メッセージを返す"""
        from weather.exceptions import JMAAreaNotFoundError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMAAreaNotFoundError(
            "内部パス: /api/weather/130010 が見つかりません"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        # 内部情報が露出せず、汎用メッセージであること
        assert "予報区コード" in response.data["error"]


@pytest.mark.django_db
class TestEveningGreetingView:
    """EveningGreetingViewのテスト"""

    @pytest.fixture
    def url(self):
        """エンドポイントURL"""
        return reverse("greeting:evening")

    @pytest.fixture
    def greeting_config(self):
        """夜のあいさつ設定"""
        return EveningGreetingConfig.objects.create(
            system_prompt="テスト用システムプロンプト",
            tts_enabled=False,
        )

    @pytest.fixture
    def greeting_config_with_tts(self):
        """TTS有効の夜のあいさつ設定"""
        return EveningGreetingConfig.objects.create(
            system_prompt="テスト用システムプロンプト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_speed=1.2,
        )

    @pytest.fixture
    def request_data(self):
        """リクエストデータ"""
        return {"user_prompt": "テスト用ユーザープロンプト"}

    @pytest.fixture
    def mock_greeting_response(self):
        """サービスのモックレスポンス（テキストのみ）"""
        return {
            "greeting_text": "お疲れ様でした、先輩。今日も一日頑張りましたね。",
        }

    @pytest.fixture
    def mock_greeting_response_with_audio(self):
        """サービスのモックレスポンス（音声あり）"""
        return {
            "greeting_text": "お疲れ様でした、先輩。今日も一日頑張りましたね。",
            "audio_data": b"RIFF....WAVEfmt ",
        }

    def test_evening_greeting_unauthorized(
        self, api_client, url, greeting_config, request_data
    ):
        """未認証の場合は401エラー"""
        response = api_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_evening_greeting_config_not_found(
        self, authenticated_client, url, request_data
    ):
        """設定が存在しない場合は404エラー"""
        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    def test_evening_greeting_missing_user_prompt(
        self, authenticated_client, url, greeting_config
    ):
        """user_promptが欠落している場合は400エラー"""
        response = authenticated_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("greeting.views.EveningGreetingService")
    def test_evening_greeting_success(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
        mock_greeting_response,
    ):
        """正常系: 挨拶がJSONで取得できる（TTS無効時）"""
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
        assert call_kwargs["system_prompt"] == "テスト用システムプロンプト"
        assert call_kwargs["user_prompt"] == "テスト用ユーザープロンプト"
        assert call_kwargs["tts_options"] is None

    @patch("greeting.views.EveningGreetingService")
    def test_evening_greeting_with_tts_enabled(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
        request_data,
        mock_greeting_response_with_audio,
    ):
        """TTS有効時: 音声データがWAVで返される"""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = mock_greeting_response_with_audio
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert "X-Greeting-Text" in response

        # TTSオプションが正しく渡されることを確認
        mock_service.generate_greeting.assert_called_once()
        call_kwargs = mock_service.generate_greeting.call_args.kwargs
        assert call_kwargs["tts_options"] is not None
        assert call_kwargs["tts_options"]["model"] == "test_model"
        assert call_kwargs["tts_options"]["style"] == "Happy"
        assert call_kwargs["tts_options"]["speed"] == 1.2

    @patch("greeting.views.EveningGreetingService")
    def test_evening_greeting_openai_timeout(
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

    @patch("greeting.views.EveningGreetingService")
    def test_evening_greeting_openai_api_error(
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
        mock_service.generate_greeting.side_effect = OpenAIAPIError("API Error")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("greeting.views.EveningGreetingService")
    def test_evening_greeting_header_sanitizes_control_chars(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
        request_data,
    ):
        """X-Greeting-Textヘッダーから制御文字が除去される"""
        from email.header import decode_header

        mock_service = MagicMock()
        # 制御文字を含むテキスト
        mock_service.generate_greeting.return_value = {
            "greeting_text": "お疲れ\r\n様でした\x00先輩",
            "audio_data": b"RIFF....WAVEfmt ",
        }
        mock_service_class.return_value = mock_service

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
        assert "お疲れ" in header_text
        assert "先輩" in header_text

    @patch("greeting.views.EveningGreetingService")
    def test_evening_greeting_holiday_api_network_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """祝日APIネットワークエラー時は502エラー"""
        from greeting.exceptions import HolidayNetworkError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = HolidayNetworkError(
            "Network error"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("greeting.views.EveningGreetingService")
    def test_evening_greeting_holiday_api_timeout(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """祝日APIタイムアウト時は504エラー"""
        from greeting.exceptions import HolidayTimeoutError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = HolidayTimeoutError("Timeout")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT


@pytest.mark.django_db
class TestWelcomeHomeGreetingView:
    """WelcomeHomeGreetingViewのテスト"""

    @pytest.fixture
    def url(self):
        """エンドポイントURL"""
        return reverse("greeting:welcome-home")

    @pytest.fixture
    def greeting_config(self):
        """おかえりのあいさつ設定"""
        return WelcomeHomeGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="テスト用システムプロンプト",
            tts_enabled=False,
        )

    @pytest.fixture
    def greeting_config_with_tts(self):
        """TTS有効のおかえりのあいさつ設定"""
        return WelcomeHomeGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="テスト用システムプロンプト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_speed=1.2,
        )

    @pytest.fixture
    def request_data(self):
        """リクエストデータ"""
        return {"user_prompt": "テスト用ユーザープロンプト"}

    @pytest.fixture
    def mock_greeting_response(self):
        """サービスのモックレスポンス（テキストのみ）"""
        return {
            "greeting_text": "おかえりなさい、先輩。今日もお疲れ様でした。",
        }

    @pytest.fixture
    def mock_greeting_response_with_audio(self):
        """サービスのモックレスポンス（音声あり）"""
        return {
            "greeting_text": "おかえりなさい、先輩。今日もお疲れ様でした。",
            "audio_data": b"RIFF....WAVEfmt ",
        }

    def test_welcome_home_greeting_unauthorized(
        self, api_client, url, greeting_config, request_data
    ):
        """未認証の場合は401エラー"""
        response = api_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_welcome_home_greeting_config_not_found(
        self, authenticated_client, url, request_data
    ):
        """設定が存在しない場合は404エラー"""
        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    def test_welcome_home_greeting_missing_user_prompt(
        self, authenticated_client, url, greeting_config
    ):
        """user_promptが欠落している場合は400エラー"""
        response = authenticated_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("greeting.views.WelcomeHomeGreetingService")
    def test_welcome_home_greeting_success(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
        mock_greeting_response,
    ):
        """正常系: 挨拶がJSONで取得できる（TTS無効時）"""
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
        assert call_kwargs["area_code"] == "130010"
        assert call_kwargs["system_prompt"] == "テスト用システムプロンプト"
        assert call_kwargs["user_prompt"] == "テスト用ユーザープロンプト"
        assert call_kwargs["tts_options"] is None

    @patch("greeting.views.WelcomeHomeGreetingService")
    def test_welcome_home_greeting_with_tts_enabled(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config_with_tts,
        request_data,
        mock_greeting_response_with_audio,
    ):
        """TTS有効時: 音声データがWAVで返される"""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = mock_greeting_response_with_audio
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert "X-Greeting-Text" in response

        # TTSオプションが正しく渡されることを確認
        mock_service.generate_greeting.assert_called_once()
        call_kwargs = mock_service.generate_greeting.call_args.kwargs
        assert call_kwargs["tts_options"] is not None
        assert call_kwargs["tts_options"]["model"] == "test_model"
        assert call_kwargs["tts_options"]["style"] == "Happy"
        assert call_kwargs["tts_options"]["speed"] == 1.2

    @patch("greeting.views.WelcomeHomeGreetingService")
    def test_welcome_home_greeting_weather_api_error(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """天気予報API失敗時に502エラー"""
        from weather.exceptions import JMANetworkError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMANetworkError("Network error")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("greeting.views.WelcomeHomeGreetingService")
    def test_welcome_home_greeting_openai_timeout(
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

    @patch("greeting.views.WelcomeHomeGreetingService")
    def test_welcome_home_greeting_area_not_found(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        request_data,
    ):
        """予報区コードが見つからない場合は404エラー"""
        from weather.exceptions import JMAAreaNotFoundError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMAAreaNotFoundError(
            "Area not found"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
