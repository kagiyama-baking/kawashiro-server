"""TTS プロキシAPI のテスト"""

from unittest.mock import Mock, patch

import pytest
import requests as requests_lib
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from core.models import User
from integrations.tts.client import TTSResult
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client):
    """認証済みのAPIクライアント"""
    user = User.objects.create_user(
        email="test@example.com",
        password="testpass123",
        name="Test User",
    )
    api_client.force_authenticate(user=user)
    return api_client


@pytest.mark.django_db
class TestTTSHealthView:
    """TTSヘルスチェックのテスト"""

    @patch("integrations.tts.views.requests.get")
    def test_health_check_with_healthy_service_returns_status(
        self, mock_get, authenticated_client
    ):
        """TTSサービスが正常な場合、ステータスを返す"""
        mock_get.return_value = Mock(
            status_code=200, json=lambda: {"status": "healthy", "models_available": 1}
        )

        response = authenticated_client.get(reverse("tts:health"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"

    @patch("integrations.tts.views.requests.get")
    def test_health_check_with_unavailable_service_returns_503(
        self, mock_get, authenticated_client
    ):
        """TTSサービスが利用不可の場合、503を返す"""
        mock_get.side_effect = requests_lib.exceptions.ConnectionError(
            "Connection refused"
        )

        response = authenticated_client.get(reverse("tts:health"))

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_health_check_without_auth_returns_401(self, api_client):
        """認証なしの場合、401を返す"""
        response = api_client.get(reverse("tts:health"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTTSModelsView:
    """TTSモデル一覧のテスト"""

    @patch("integrations.tts.views.requests.get")
    def test_models_list_returns_available_models(self, mock_get, authenticated_client):
        """利用可能なモデル一覧を返す"""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"models": ["model1", "model2"], "default": "model1"},
        )

        response = authenticated_client.get(reverse("tts:models"))

        assert response.status_code == status.HTTP_200_OK
        assert "models" in response.data

    @patch("integrations.tts.views.requests.get")
    def test_models_list_with_unavailable_service_returns_503(
        self, mock_get, authenticated_client
    ):
        """TTSサービスが利用不可の場合、503を返す"""
        mock_get.side_effect = requests_lib.exceptions.ConnectionError(
            "Connection refused"
        )

        response = authenticated_client.get(reverse("tts:models"))

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_models_list_without_auth_returns_401(self, api_client):
        """認証なしの場合、401を返す"""
        response = api_client.get(reverse("tts:models"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTTSModelStylesView:
    """TTSモデルスタイル一覧のテスト"""

    @patch("integrations.tts.views.requests.get")
    def test_model_styles_returns_available_styles(
        self, mock_get, authenticated_client
    ):
        """指定モデルのスタイル一覧を返す"""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"model": "test_model", "styles": ["Neutral", "Happy"]},
        )

        response = authenticated_client.get(
            reverse("tts:model-styles", args=["test_model"])
        )

        assert response.status_code == status.HTTP_200_OK
        assert "styles" in response.data

    @patch("integrations.tts.views.requests.get")
    def test_model_styles_with_unavailable_service_returns_503(
        self, mock_get, authenticated_client
    ):
        """TTSサービスが利用不可の場合、503を返す"""
        mock_get.side_effect = requests_lib.exceptions.ConnectionError(
            "Connection refused"
        )

        response = authenticated_client.get(
            reverse("tts:model-styles", args=["test_model"])
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_model_styles_rejects_path_traversal(self, authenticated_client):
        """パストラバーサルを含むモデル名は400を返す"""
        # URLパターンが[^/]+なので、..を含むがスラッシュなしのケースをテスト
        response = authenticated_client.get(
            reverse("tts:model-styles", args=["..etc..passwd"])
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_model_styles_rejects_special_characters(self, authenticated_client):
        """特殊文字を含むモデル名は400を返す"""
        response = authenticated_client.get(
            reverse("tts:model-styles", args=["model;drop"])
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_model_styles_without_auth_returns_401(self, api_client):
        """認証なしの場合、401を返す"""
        response = api_client.get(reverse("tts:model-styles", args=["test_model"]))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTTSSynthesizeView:
    """音声合成プロキシのテスト"""

    @pytest.fixture
    def mock_tts_result_mp3(self):
        """MP3フォーマットのTTSResult"""
        return TTSResult(
            audio_data=b"fake mp3 data",
            content_type="audio/mpeg",
            format="mp3",
        )

    @pytest.fixture
    def mock_tts_result_wav(self):
        """WAVフォーマットのTTSResult"""
        return TTSResult(
            audio_data=b"RIFF....WAVEfmt ",
            content_type="audio/wav",
            format="wav",
        )

    @patch("integrations.tts.views.TTSClient")
    def test_synthesize_get_default_returns_wav(
        self, mock_client_class, authenticated_client, mock_tts_result_wav
    ):
        """GETリクエストのデフォルトでWAVが返される"""
        mock_client = Mock()
        mock_client.synthesize.return_value = mock_tts_result_wav
        mock_client_class.return_value = mock_client

        response = authenticated_client.get(
            f"{reverse('tts:synthesize')}?text=こんにちは"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert "inline" in response["Content-Disposition"]
        assert ".wav" in response["Content-Disposition"]

    @patch("integrations.tts.views.TTSClient")
    def test_synthesize_post_returns_wav_attachment(
        self, mock_client_class, authenticated_client, mock_tts_result_wav
    ):
        """POSTリクエストでWAVがattachmentで返される"""
        mock_client = Mock()
        mock_client.synthesize.return_value = mock_tts_result_wav
        mock_client_class.return_value = mock_client

        response = authenticated_client.post(
            reverse("tts:synthesize"),
            data={"text": "こんにちは"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert "attachment" in response["Content-Disposition"]

    @patch("integrations.tts.views.TTSClient")
    def test_synthesize_with_wav_format_returns_audio_wav(
        self, mock_client_class, authenticated_client, mock_tts_result_wav
    ):
        """WAVフォーマット指定時にaudio/wavが返される"""
        mock_client = Mock()
        mock_client.synthesize.return_value = mock_tts_result_wav
        mock_client_class.return_value = mock_client

        response = authenticated_client.get(
            f"{reverse('tts:synthesize')}?text=こんにちは&format=wav"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "audio/wav"
        assert ".wav" in response["Content-Disposition"]

    def test_synthesize_post_without_text_returns_400(self, authenticated_client):
        """POSTリクエストでtextパラメータがない場合、400を返す"""
        response = authenticated_client.post(
            reverse("tts:synthesize"),
            data={"style": "Happy"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_synthesize_post_with_invalid_speed_returns_400(self, authenticated_client):
        """POSTリクエストでspeedパラメータの範囲外の場合、400を返す"""
        response = authenticated_client.post(
            reverse("tts:synthesize"),
            data={"text": "テスト", "speed": 10.0},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_synthesize_post_with_invalid_format_returns_400(
        self, authenticated_client
    ):
        """不正なフォーマット指定時に400を返す"""
        response = authenticated_client.post(
            reverse("tts:synthesize"),
            data={"text": "テスト", "format": "aac"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_synthesize_without_text_returns_400(self, authenticated_client):
        """textパラメータがない場合、400を返す"""
        response = authenticated_client.get(reverse("tts:synthesize"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("integrations.tts.views.TTSClient")
    def test_synthesize_with_timeout_returns_504(
        self, mock_client_class, authenticated_client
    ):
        """タイムアウト時は504を返す"""
        mock_client = Mock()
        mock_client.synthesize.side_effect = TTSTimeoutError("Timeout")
        mock_client_class.return_value = mock_client

        response = authenticated_client.get(
            f"{reverse('tts:synthesize')}?text=こんにちは"
        )

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    @patch("integrations.tts.views.TTSClient")
    def test_synthesize_with_connection_error_returns_503(
        self, mock_client_class, authenticated_client
    ):
        """接続エラー時は503を返す"""
        mock_client = Mock()
        mock_client.synthesize.side_effect = TTSNetworkError("Connection refused")
        mock_client_class.return_value = mock_client

        response = authenticated_client.get(
            f"{reverse('tts:synthesize')}?text=こんにちは"
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("integrations.tts.views.TTSClient")
    def test_synthesize_get_with_all_parameters(
        self, mock_client_class, authenticated_client, mock_tts_result_mp3
    ):
        """全パラメータを指定してGETリクエストで音声合成が成功する"""
        mock_client = Mock()
        mock_client.synthesize.return_value = mock_tts_result_mp3
        mock_client_class.return_value = mock_client

        url = (
            f"{reverse('tts:synthesize')}?"
            "text=こんにちは&"
            "model=custom_model&"
            "style=Happy&"
            "style_weight=1.5&"
            "speed=1.2&"
            "sdp_ratio=0.3&"
            "noise_scale=0.7&"
            "noise_scale_w=0.9&"
            "format=mp3"
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_synthesize_without_auth_returns_401(self, api_client):
        """認証なしの場合、401を返す"""
        response = api_client.get(f"{reverse('tts:synthesize')}?text=こんにちは")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
