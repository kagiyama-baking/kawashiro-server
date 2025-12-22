"""
TTS プロキシAPI
内部のStyle-BERT-VITS2サービスへリクエストを転送する
"""

import logging

import requests
from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from .renderers import AudioWavRenderer
from .serializers import TTSSynthesizeSerializer

logger = logging.getLogger(__name__)

# 内部TTSサービスのURL（Docker内部ネットワーク）
TTS_SERVICE_URL = getattr(settings, "TTS_SERVICE_URL", "http://sbv2-api:5000")
TTS_TIMEOUT = getattr(settings, "TTS_TIMEOUT", 60)  # 音声合成は時間がかかる


class TTSHealthView(APIView):
    """TTSサービスのヘルスチェック"""

    def get(self, request):
        try:
            response = requests.get(f"{TTS_SERVICE_URL}/health", timeout=10)
            return Response(response.json(), status=response.status_code)
        except requests.exceptions.RequestException as e:
            logger.error(f"TTS health check failed: {e}")
            return Response(
                {"status": "unhealthy", "error": "TTS service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class TTSModelsView(APIView):
    """利用可能なモデル一覧"""

    def get(self, request):
        try:
            response = requests.get(f"{TTS_SERVICE_URL}/models", timeout=10)
            return Response(response.json(), status=response.status_code)
        except requests.exceptions.RequestException as e:
            logger.error(f"TTS models request failed: {e}")
            return Response(
                {"error": "TTS service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class TTSModelStylesView(APIView):
    """指定モデルのスタイル一覧"""

    def get(self, request, model_name):
        try:
            response = requests.get(
                f"{TTS_SERVICE_URL}/models/{model_name}/styles",
                timeout=10,
            )
            return Response(response.json(), status=response.status_code)
        except requests.exceptions.RequestException as e:
            logger.error(f"TTS styles request failed: {e}")
            return Response(
                {"error": "TTS service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class TTSSynthesizeView(APIView):
    """音声合成プロキシ"""

    renderer_classes = [AudioWavRenderer, JSONRenderer]

    @extend_schema(
        parameters=[TTSSynthesizeSerializer],
        responses={
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
        return self._synthesize(request.query_params, inline=True)

    @extend_schema(
        request=TTSSynthesizeSerializer,
        responses={
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
        """内部TTSサービスに転送して音声を取得"""
        # 必須パラメータチェック
        text = params.get("text")
        if not text:
            return Response(
                {"error": "text parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # パラメータを構築
        tts_params = {
            "text": text,
            "model": params.get("model"),
            "style": params.get("style", "Neutral"),
            "style_weight": params.get("style_weight", 1.0),
            "speed": params.get("speed", 1.0),
            "sdp_ratio": params.get("sdp_ratio", 0.2),
            "noise_scale": params.get("noise_scale", 0.6),
            "noise_scale_w": params.get("noise_scale_w", 0.8),
        }
        # Noneを除去
        tts_params = {k: v for k, v in tts_params.items() if v is not None}

        try:
            logger.info(f"TTS request: text={text}")

            response = requests.post(
                f"{TTS_SERVICE_URL}/synthesize",
                json=tts_params,
                timeout=TTS_TIMEOUT,
            )

            if response.status_code != 200:
                return Response(response.json(), status=response.status_code)

            # 音声データをそのまま返す
            resp = Response(
                response.content,
                status=status.HTTP_200_OK,
                content_type="audio/wav",
            )
            # inline: ブラウザ内再生、attachment: ダウンロード
            disposition = "inline" if inline else "attachment"
            resp["Content-Disposition"] = f'{disposition}; filename="tts_output.wav"'
            resp["X-TTS-Model"] = response.headers.get("X-Model", "")
            resp["X-TTS-Style"] = response.headers.get("X-Style", "")
            return resp

        except requests.exceptions.Timeout:
            logger.error("TTS request timeout")
            return Response(
                {"error": "TTS service timeout"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"TTS request failed: {e}")
            return Response(
                {"error": "TTS service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
