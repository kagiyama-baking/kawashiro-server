"""
TTS プロキシAPI
内部のStyle-BERT-VITS2サービスへリクエストを転送する
"""

import logging
import re

import requests
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from .client import TTS_SERVICE_URL, TTSClient
from .exceptions import TTSNetworkError, TTSTimeoutError
from .renderers import AudioMp3Renderer, AudioOggRenderer, AudioWavRenderer
from .serializers import TTSSynthesizeSerializer

logger = logging.getLogger(__name__)

# フォーマットごとのファイル拡張子
FORMAT_EXTENSIONS = {
    "wav": "wav",
    "mp3": "mp3",
    "ogg": "ogg",
}


class TTSHealthView(APIView):
    """TTSサービスのヘルスチェック"""

    def get(self, request):
        try:
            response = requests.get(f"{TTS_SERVICE_URL}/health", timeout=10)
            try:
                data = response.json()
            except ValueError:
                return Response(
                    {
                        "status": "unhealthy",
                        "error": "Invalid response from TTS service",
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return Response(data, status=response.status_code)
        except requests.exceptions.RequestException as e:
            logger.error("TTS health check failed: %s", e)
            return Response(
                {"status": "unhealthy", "error": "TTS service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class TTSModelsView(APIView):
    """利用可能なモデル一覧"""

    def get(self, request):
        try:
            response = requests.get(f"{TTS_SERVICE_URL}/models", timeout=10)
            try:
                data = response.json()
            except ValueError:
                return Response(
                    {"error": "Invalid response from TTS service"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return Response(data, status=response.status_code)
        except requests.exceptions.RequestException as e:
            logger.error("TTS models request failed: %s", e)
            return Response(
                {"error": "TTS service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class TTSModelStylesView(APIView):
    """指定モデルのスタイル一覧"""

    def get(self, request, model_name):
        # パストラバーサル防止: 英数字・ハイフン・アンダースコアのみ許可
        if not re.match(r"^[a-zA-Z0-9_\-]+$", model_name):
            return Response(
                {"error": "Invalid model name"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            response = requests.get(
                f"{TTS_SERVICE_URL}/models/{model_name}/styles",
                timeout=10,
            )
            try:
                data = response.json()
            except ValueError:
                return Response(
                    {"error": "Invalid response from TTS service"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return Response(data, status=response.status_code)
        except requests.exceptions.RequestException as e:
            logger.error("TTS styles request failed: %s", e)
            return Response(
                {"error": "TTS service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class TTSSynthesizeView(APIView):
    """音声合成プロキシ"""

    renderer_classes = [
        AudioMp3Renderer,
        AudioWavRenderer,
        AudioOggRenderer,
        JSONRenderer,
    ]

    @extend_schema(
        parameters=[TTSSynthesizeSerializer],
        responses={
            (200, "audio/mpeg"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ(MP3形式、デフォルト)",
            ),
            (200, "audio/wav"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ(WAV形式)",
            ),
            400: OpenApiResponse(description="パラメータエラー"),
            503: OpenApiResponse(description="TTSサービス接続エラー"),
            504: OpenApiResponse(description="TTSサービスタイムアウト"),
        },
        description="テキストから音声を合成します（ブラウザで直接再生可能）",
    )
    def get(self, request):
        """GETリクエストで音声合成（ブラウザ再生・埋め込み用）"""
        serializer = TTSSynthesizeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return self._synthesize(serializer.validated_data, inline=True)

    @extend_schema(
        request=TTSSynthesizeSerializer,
        responses={
            (200, "audio/mpeg"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ(MP3形式、デフォルト)",
            ),
            (200, "audio/wav"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ(WAV形式)",
            ),
            400: OpenApiResponse(description="パラメータエラー"),
            503: OpenApiResponse(description="TTSサービス接続エラー"),
            504: OpenApiResponse(description="TTSサービスタイムアウト"),
        },
        description="テキストから音声を合成します（ファイルダウンロード用）",
    )
    def post(self, request):
        """POSTリクエストで音声合成（ダウンロード用）"""
        serializer = TTSSynthesizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._synthesize(serializer.validated_data, inline=False)

    def _synthesize(self, params, inline=True):
        """TTSClientを使用して音声を合成"""
        # 必須パラメータチェック
        text = params.get("text")
        if not text:
            return Response(
                {"error": "text parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        audio_format = params.get("format", "mp3")

        try:
            client = TTSClient()
            result = client.synthesize(
                text=text,
                model=params.get("model"),
                style=params.get("style", "Neutral"),
                style_weight=params.get("style_weight", 1.0),
                speed=params.get("speed", 1.0),
                sdp_ratio=params.get("sdp_ratio", 0.2),
                noise_scale=params.get("noise_scale", 0.6),
                noise_scale_w=params.get("noise_scale_w", 0.8),
                format=audio_format,
            )

            ext = FORMAT_EXTENSIONS.get(audio_format, "mp3")
            disposition = "inline" if inline else "attachment"
            resp = Response(
                result.audio_data,
                status=status.HTTP_200_OK,
                content_type=result.content_type,
            )
            resp["Content-Disposition"] = f'{disposition}; filename="tts_output.{ext}"'
            return resp

        except TTSTimeoutError:
            logger.error("TTS request timeout")
            return Response(
                {"error": "TTS service timeout"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except TTSNetworkError as e:
            logger.error("TTS request failed: %s", e)
            return Response(
                {"error": "TTS service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
