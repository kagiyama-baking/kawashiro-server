"""TTSサービスクライアント."""

import logging
from typing import Any

import requests
from django.conf import settings

from .exceptions import TTSNetworkError, TTSTimeoutError

logger = logging.getLogger(__name__)

# 内部TTSサービスのURL（Docker内部ネットワーク）
TTS_SERVICE_URL = getattr(settings, "TTS_SERVICE_URL", "http://sbv2-api:5000")
TTS_TIMEOUT = getattr(settings, "TTS_TIMEOUT", 60)


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
    ) -> bytes:
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

        Returns:
            WAV形式の音声データ（bytes）

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
        }

        if model is not None:
            params["model"] = model

        try:
            logger.info(
                "TTS合成リクエスト: text=%s...", text[:50] if len(text) > 50 else text
            )

            response = requests.post(
                f"{self.service_url}/synthesize",
                json=params,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                error_msg = response.json().get("error", "Unknown error")
                raise TTSNetworkError(f"TTSサービスエラー: {error_msg}")

            logger.info("TTS合成完了: %d bytes", len(response.content))
            return response.content

        except requests.exceptions.Timeout as e:
            logger.error("TTSサービスタイムアウト: %s", str(e))
            raise TTSTimeoutError(
                "TTSサービスへのリクエストがタイムアウトしました"
            ) from e

        except requests.exceptions.RequestException as e:
            logger.error("TTSサービス接続エラー: %s", str(e))
            raise TTSNetworkError(f"TTSサービスへの接続に失敗しました: {e}") from e
