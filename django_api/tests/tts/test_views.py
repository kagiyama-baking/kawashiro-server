"""TTS プロキシAPI のテスト"""

from unittest.mock import Mock, patch

import pytest
import requests as requests_lib
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


class TestTTSHealthView:
    """TTSヘルスチェックのテスト"""

    @patch("tts.views.requests.get")
    def test_health_check_with_healthy_service_returns_status(
        self, mock_get, api_client
    ):
        """TTSサービスが正常な場合、ステータスを返す"""
        mock_get.return_value = Mock(
            status_code=200, json=lambda: {"status": "healthy", "models_available": 1}
        )

        response = api_client.get(reverse("tts:health"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"

    @patch("tts.views.requests.get")
    def test_health_check_with_unavailable_service_returns_503(
        self, mock_get, api_client
    ):
        """TTSサービスが利用不可の場合、503を返す"""
        mock_get.side_effect = requests_lib.exceptions.ConnectionError(
            "Connection refused"
        )

        response = api_client.get(reverse("tts:health"))

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


class TestTTSModelsView:
    """TTSモデル一覧のテスト"""

    @patch("tts.views.requests.get")
    def test_models_list_returns_available_models(self, mock_get, api_client):
        """利用可能なモデル一覧を返す"""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"models": ["model1", "model2"], "default": "model1"},
        )

        response = api_client.get(reverse("tts:models"))

        assert response.status_code == status.HTTP_200_OK
        assert "models" in response.data

    @patch("tts.views.requests.get")
    def test_models_list_with_unavailable_service_returns_503(
        self, mock_get, api_client
    ):
        """TTSサービスが利用不可の場合、503を返す"""
        mock_get.side_effect = requests_lib.exceptions.ConnectionError(
            "Connection refused"
        )

        response = api_client.get(reverse("tts:models"))

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


class TestTTSModelStylesView:
    """TTSモデルスタイル一覧のテスト"""

    @patch("tts.views.requests.get")
    def test_model_styles_returns_available_styles(self, mock_get, api_client):
        """指定モデルのスタイル一覧を返す"""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"model": "test_model", "styles": ["Neutral", "Happy"]},
        )

        response = api_client.get(reverse("tts:model-styles", args=["test_model"]))

        assert response.status_code == status.HTTP_200_OK
        assert "styles" in response.data

    @patch("tts.views.requests.get")
    def test_model_styles_with_unavailable_service_returns_503(
        self, mock_get, api_client
    ):
        """TTSサービスが利用不可の場合、503を返す"""
        mock_get.side_effect = requests_lib.exceptions.ConnectionError(
            "Connection refused"
        )

        response = api_client.get(reverse("tts:model-styles", args=["test_model"]))

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


class TestTTSSynthesizeView:
    """音声合成プロキシのテスト"""

    @patch("tts.views.requests.get")
    def test_synthesize_get_with_valid_text_returns_audio_inline(
        self, mock_get, api_client
    ):
        """GETリクエストで音声合成が成功し、inlineで返す"""
        mock_get.return_value = Mock(
            status_code=200,
            content=b"fake audio data",
            headers={"X-Model": "test", "X-Style": "Neutral"},
        )

        response = api_client.get(f"{reverse('tts:synthesize')}?text=こんにちは")

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert "inline" in response["Content-Disposition"]

    @patch("tts.views.requests.get")
    def test_synthesize_post_with_valid_text_returns_audio_attachment(
        self, mock_get, api_client
    ):
        """POSTリクエストで音声合成が成功し、attachmentで返す"""
        mock_get.return_value = Mock(
            status_code=200,
            content=b"fake audio data",
            headers={"X-Model": "test", "X-Style": "Neutral"},
        )

        response = api_client.post(f"{reverse('tts:synthesize')}?text=こんにちは")

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert "attachment" in response["Content-Disposition"]

    def test_synthesize_without_text_returns_400(self, api_client):
        """textパラメータがない場合、400を返す"""
        response = api_client.get(reverse("tts:synthesize"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "text" in response.data["error"]

    @patch("tts.views.requests.get")
    def test_synthesize_with_timeout_returns_504(self, mock_get, api_client):
        """タイムアウト時は504を返す"""
        mock_get.side_effect = requests_lib.exceptions.Timeout()

        response = api_client.get(f"{reverse('tts:synthesize')}?text=こんにちは")

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    @patch("tts.views.requests.get")
    def test_synthesize_with_connection_error_returns_503(self, mock_get, api_client):
        """接続エラー時は503を返す"""
        mock_get.side_effect = requests_lib.exceptions.ConnectionError()

        response = api_client.get(f"{reverse('tts:synthesize')}?text=こんにちは")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("tts.views.requests.get")
    def test_synthesize_get_with_all_parameters(self, mock_get, api_client):
        """全パラメータを指定してGETリクエストで音声合成が成功する"""
        mock_get.return_value = Mock(
            status_code=200,
            content=b"fake audio data",
            headers={"X-Model": "custom_model", "X-Style": "Happy"},
        )

        url = (
            f"{reverse('tts:synthesize')}?"
            "text=こんにちは&"
            "model=custom_model&"
            "style=Happy&"
            "style_weight=1.5&"
            "speed=1.2&"
            "sdp_ratio=0.3&"
            "noise_scale=0.7&"
            "noise_scale_w=0.9"
        )
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    @patch("tts.views.requests.get")
    def test_synthesize_forwards_error_response(self, mock_get, api_client):
        """TTSサービスからのエラーレスポンスを転送する"""
        mock_get.return_value = Mock(
            status_code=400,
            json=lambda: {"detail": "Invalid style"},
        )

        response = api_client.get(f"{reverse('tts:synthesize')}?text=こんにちは")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
