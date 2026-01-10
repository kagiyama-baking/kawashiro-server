"""TTSクライアントのテスト."""

from unittest.mock import Mock, patch

import pytest
import requests

from tts.client import TTSClient
from tts.exceptions import TTSNetworkError, TTSTimeoutError


class TestTTSClient:
    """TTSClientのテスト."""

    @pytest.fixture
    def tts_client(self):
        """TTSクライアントのフィクスチャ."""
        return TTSClient()

    def test_synthesize_success(self, tts_client):
        """正常系: 音声合成が成功する."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"RIFF....WAVEfmt "  # ダミーWAVデータ

        with patch("tts.client.requests.post", return_value=mock_response) as mock_post:
            result = tts_client.synthesize(
                text="こんにちは",
                style="Neutral",
                speed=1.0,
            )

            assert result == b"RIFF....WAVEfmt "
            mock_post.assert_called_once()

            # リクエストパラメータの検証
            call_args = mock_post.call_args
            assert call_args[1]["json"]["text"] == "こんにちは"
            assert call_args[1]["json"]["style"] == "Neutral"
            assert call_args[1]["json"]["speed"] == 1.0

    def test_synthesize_with_model(self, tts_client):
        """モデル指定時にパラメータに含まれる."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"WAV_DATA"

        with patch("tts.client.requests.post", return_value=mock_response) as mock_post:
            tts_client.synthesize(
                text="テスト",
                model="custom_model",
            )

            call_args = mock_post.call_args
            assert call_args[1]["json"]["model"] == "custom_model"

    def test_synthesize_timeout(self, tts_client):
        """タイムアウト時にTTSTimeoutErrorを発生させる."""
        with patch(
            "tts.client.requests.post",
            side_effect=requests.exceptions.Timeout("Timeout"),
        ):
            with pytest.raises(TTSTimeoutError) as exc_info:
                tts_client.synthesize(text="テスト")

            assert "タイムアウト" in str(exc_info.value)

    def test_synthesize_connection_error(self, tts_client):
        """接続エラー時にTTSNetworkErrorを発生させる."""
        with patch(
            "tts.client.requests.post",
            side_effect=requests.exceptions.ConnectionError("Connection refused"),
        ):
            with pytest.raises(TTSNetworkError) as exc_info:
                tts_client.synthesize(text="テスト")

            assert "接続に失敗" in str(exc_info.value)

    def test_synthesize_api_error(self, tts_client):
        """APIエラー時にTTSNetworkErrorを発生させる."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal server error"}

        with patch("tts.client.requests.post", return_value=mock_response):
            with pytest.raises(TTSNetworkError) as exc_info:
                tts_client.synthesize(text="テスト")

            assert "Internal server error" in str(exc_info.value)

    def test_synthesize_default_params(self, tts_client):
        """デフォルトパラメータが正しく設定される."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"WAV_DATA"

        with patch("tts.client.requests.post", return_value=mock_response) as mock_post:
            tts_client.synthesize(text="テスト")

            call_args = mock_post.call_args
            params = call_args[1]["json"]
            assert params["style"] == "Neutral"
            assert params["style_weight"] == 1.0
            assert params["speed"] == 1.0
            assert params["sdp_ratio"] == 0.2
            assert params["noise_scale"] == 0.6
            assert params["noise_scale_w"] == 0.8
