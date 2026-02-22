"""TTSクライアントのテスト."""

from unittest.mock import Mock, patch

import pytest
import requests

from tts.client import TTSClient, TTSResult
from tts.exceptions import TTSNetworkError, TTSTimeoutError


class TestTTSResult:
    """TTSResultのテスト."""

    def test_tts_result_is_immutable(self):
        """TTSResultはイミュータブルである."""
        result = TTSResult(
            audio_data=b"test",
            content_type="audio/mpeg",
            format="mp3",
        )
        with pytest.raises(AttributeError):
            result.audio_data = b"changed"

    def test_tts_result_stores_all_fields(self):
        """TTSResultがすべてのフィールドを保持する."""
        result = TTSResult(
            audio_data=b"audio_bytes",
            content_type="audio/wav",
            format="wav",
        )
        assert result.audio_data == b"audio_bytes"
        assert result.content_type == "audio/wav"
        assert result.format == "wav"


class TestTTSClient:
    """TTSClientのテスト."""

    @pytest.fixture
    def tts_client(self):
        """TTSクライアントのフィクスチャ."""
        return TTSClient()

    def test_synthesize_success_returns_tts_result(self, tts_client):
        """正常系: TTSResultが返される."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake_mp3_data"
        mock_response.headers = {"Content-Type": "audio/mpeg"}

        with patch("tts.client.requests.post", return_value=mock_response):
            result = tts_client.synthesize(
                text="こんにちは",
                style="Neutral",
                speed=1.0,
            )

            assert isinstance(result, TTSResult)
            assert result.audio_data == b"fake_mp3_data"
            assert result.content_type == "audio/mpeg"
            assert result.format == "mp3"

    def test_synthesize_default_format_is_mp3(self, tts_client):
        """デフォルトフォーマットがmp3."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"mp3_data"
        mock_response.headers = {"Content-Type": "audio/mpeg"}

        with patch("tts.client.requests.post", return_value=mock_response) as mock_post:
            tts_client.synthesize(text="テスト")

            call_args = mock_post.call_args
            assert call_args[1]["json"]["format"] == "mp3"

    def test_synthesize_sends_format_parameter(self, tts_client):
        """formatパラメータがSBV2に送信される."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"wav_data"
        mock_response.headers = {"Content-Type": "audio/wav"}

        with patch("tts.client.requests.post", return_value=mock_response) as mock_post:
            tts_client.synthesize(text="テスト", format="wav")

            call_args = mock_post.call_args
            assert call_args[1]["json"]["format"] == "wav"

    def test_synthesize_wav_format(self, tts_client):
        """WAVフォーマットで合成できる."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"RIFF....WAVEfmt "
        mock_response.headers = {"Content-Type": "audio/wav"}

        with patch("tts.client.requests.post", return_value=mock_response):
            result = tts_client.synthesize(text="テスト", format="wav")

            assert result.format == "wav"
            assert result.content_type == "audio/wav"

    def test_synthesize_with_model(self, tts_client):
        """モデル指定時にパラメータに含まれる."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"MP3_DATA"
        mock_response.headers = {"Content-Type": "audio/mpeg"}

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
        mock_response.content = b"MP3_DATA"
        mock_response.headers = {"Content-Type": "audio/mpeg"}

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
            assert params["format"] == "mp3"

    def test_synthesize_content_type_from_response_header(self, tts_client):
        """Content-Typeがレスポンスヘッダーから取得される."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"ogg_data"
        mock_response.headers = {"Content-Type": "audio/ogg"}

        with patch("tts.client.requests.post", return_value=mock_response):
            result = tts_client.synthesize(text="テスト", format="ogg")

            assert result.content_type == "audio/ogg"

    def test_synthesize_api_error_non_json_response(self, tts_client):
        """APIエラーでJSONでないレスポンスの場合も適切に処理される."""
        mock_response = Mock()
        mock_response.status_code = 502
        mock_response.json.side_effect = ValueError("No JSON")

        with patch("tts.client.requests.post", return_value=mock_response):
            with pytest.raises(TTSNetworkError) as exc_info:
                tts_client.synthesize(text="テスト")

            assert "HTTP 502" in str(exc_info.value)
