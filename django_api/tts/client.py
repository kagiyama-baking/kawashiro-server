"""TTSサービスクライアント."""

import logging
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

from core.metrics import EXTERNAL_API_DURATION

from .exceptions import TTSNetworkError, TTSTimeoutError

logger = logging.getLogger(__name__)

# 内部TTSサービスのURL（Docker内部ネットワーク）
TTS_SERVICE_URL = getattr(settings, "TTS_SERVICE_URL", "http://sbv2-api:5000")
TTS_TIMEOUT = getattr(settings, "TTS_TIMEOUT", 120)

# フォーマットとContent-Typeのマッピング
FORMAT_CONTENT_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
}


@dataclass(frozen=True)
class TTSResult:
    """音声合成結果."""

    audio_data: bytes
    content_type: str
    format: str


class TTSClient:
    """TTSサービスへのクライアント."""

    def __init__(self):
        """クライアントを初期化."""
        self.service_url = TTS_SERVICE_URL
        self.timeout = TTS_TIMEOUT

    def synthesize(
        self,
        text: str,
        model: str | None = None,
        style: str = "Neutral",
        style_weight: float = 1.0,
        speed: float = 1.0,
        sdp_ratio: float = 0.2,
        noise_scale: float = 0.6,
        noise_scale_w: float = 0.8,
        format: str = "wav",
    ) -> TTSResult:
        """テキストから音声を合成.

        Args:
            text: 合成するテキスト
            model: 使用するモデル名（省略時はデフォルト）
            style: スタイル名
            style_weight: スタイルの強さ
            speed: 話速
            sdp_ratio: SDP比率
            noise_scale: ノイズスケール
            noise_scale_w: ノイズスケールW
            format: 出力フォーマット（wav, mp3, ogg）

        Returns:
            TTSResult: 音声データ、Content-Type、フォーマットを含む結果

        Raises:
            TTSTimeoutError: タイムアウト時
            TTSNetworkError: ネットワークエラー時
        """
        params: dict[str, Any] = {
            "text": text,
            "style": style,
            "style_weight": style_weight,
            "speed": speed,
            "sdp_ratio": sdp_ratio,
            "noise_scale": noise_scale,
            "noise_scale_w": noise_scale_w,
            "format": format,
        }

        if model is not None:
            params["model"] = model

        try:
            logger.info(
                "TTS合成リクエスト: text=%s...", text[:50] if len(text) > 50 else text
            )

            with EXTERNAL_API_DURATION.labels(
                service="tts", method="synthesize"
            ).time():
                response = requests.post(
                    f"{self.service_url}/synthesize",
                    json=params,
                    timeout=self.timeout,
                )

            if response.status_code != 200:
                try:
                    error_msg = response.json().get("error", "Unknown error")
                except (ValueError, KeyError):
                    error_msg = f"HTTP {response.status_code}"
                raise TTSNetworkError(f"TTSサービスエラー: {error_msg}")

            content_type = response.headers.get(
                "Content-Type",
                FORMAT_CONTENT_TYPES.get(format, "audio/mpeg"),
            )

            logger.info(
                "TTS合成完了: %d bytes, format=%s", len(response.content), format
            )
            return TTSResult(
                audio_data=response.content,
                content_type=content_type,
                format=format,
            )

        except requests.exceptions.Timeout as e:
            logger.error("TTSサービスタイムアウト: %s", str(e))
            raise TTSTimeoutError(
                "TTSサービスへのリクエストがタイムアウトしました"
            ) from e

        except requests.exceptions.RequestException as e:
            logger.error("TTSサービス接続エラー: %s", str(e))
            raise TTSNetworkError(f"TTSサービスへの接続に失敗しました: {e}") from e
