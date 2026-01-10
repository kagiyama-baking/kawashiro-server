"""Tests for greeting views."""

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from greeting.models import MorningGreetingConfig


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
            rail_ids="131,22",
            system_prompt="テスト用システムプロンプト",
            user_prompt="テスト用ユーザープロンプト",
            tts_enabled=False,
        )

    @pytest.fixture
    def greeting_config_with_tts(self):
        """TTS有効の朝のあいさつ設定"""
        return MorningGreetingConfig.objects.create(
            area_code="130010",
            rail_ids="131,22",
            system_prompt="テスト用システムプロンプト",
            user_prompt="テスト用ユーザープロンプト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_speed=1.2,
        )

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

    def test_morning_greeting_unauthorized(self, api_client, url, greeting_config):
        """未認証の場合は401エラー"""
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_morning_greeting_config_not_found(self, authenticated_client, url):
        """設定が存在しない場合は404エラー"""
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_success(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
        mock_greeting_response,
    ):
        """正常系: 挨拶がJSONで取得できる（TTS無効時）"""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = mock_greeting_response
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "greeting_text" in response.data
        assert response.data["greeting_text"] == mock_greeting_response["greeting_text"]

        # サービスが正しい引数で呼ばれたことを確認
        mock_service.generate_greeting.assert_called_once()
        call_kwargs = mock_service.generate_greeting.call_args.kwargs
        assert call_kwargs["area_code"] == "130010"
        assert call_kwargs["rail_ids"] == ["131", "22"]
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
        mock_greeting_response_with_audio,
    ):
        """TTS有効時: 音声データがWAVで返される"""
        mock_service = MagicMock()
        mock_service.generate_greeting.return_value = mock_greeting_response_with_audio
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(url)

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
    ):
        """天気予報API失敗時に502エラー"""
        from weather.exceptions import JMANetworkError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMANetworkError("Network error")
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_openai_timeout(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
    ):
        """OpenAI APIタイムアウト時に504エラー"""
        from llm_client.exceptions import OpenAITimeoutError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = OpenAITimeoutError("Timeout")
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_area_not_found(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
    ):
        """予報区コードが見つからない場合は404エラー"""
        from weather.exceptions import JMAAreaNotFoundError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMAAreaNotFoundError(
            "Area not found"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_rail_not_found(
        self,
        mock_service_class,
        authenticated_client,
        url,
        greeting_config,
    ):
        """路線IDが見つからない場合は404エラー"""
        from train.exceptions import YahooRailNotFoundError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = YahooRailNotFoundError(
            "Rail not found"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("greeting.views.MorningGreetingService")
    def test_morning_greeting_header_sanitizes_control_chars(
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
            "audio_data": b"RIFF....WAVEfmt ",
        }
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(url)

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
    ):
        """予報区コードエラー時は汎用メッセージを返す"""
        from weather.exceptions import JMAAreaNotFoundError

        mock_service = MagicMock()
        mock_service.generate_greeting.side_effect = JMAAreaNotFoundError(
            "内部パス: /api/weather/130010 が見つかりません"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        # 内部情報が露出せず、汎用メッセージであること
        assert "予報区コード" in response.data["error"]
