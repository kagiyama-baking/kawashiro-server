"""アシスタントAPI ビュー."""

import base64
import logging

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from outlook.ms_graph_client import OutlookGraphClient
from weather.jma_client import JMAWeatherClient

from .exceptions import AssistantError, OpenAIConfigurationError
from .openai_client import OpenAIClient
from .serializers import (
    ChatRequestSerializer,
    ChatResponseSerializer,
    DailySummaryRequestSerializer,
    DailySummaryResponseSerializer,
    GreetingRequestSerializer,
    GreetingResponseSerializer,
)
from .services import AssistantService

logger = logging.getLogger(__name__)


def get_tts_service_url() -> str:
    """TTSサービスのURLを取得."""
    return getattr(settings, "TTS_SERVICE_URL", "http://sbv2-api:5000")


class GreetingView(APIView):
    """挨拶生成API."""

    @extend_schema(
        request=GreetingRequestSerializer,
        responses={200: GreetingResponseSerializer},
        description="今日の予定と天気を元に挨拶を生成します",
        tags=["assistant"],
    )
    def post(self, request):
        """挨拶を生成."""
        serializer = GreetingRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            service = self._create_service()
            result = service.generate_greeting(
                area_code=data["area_code"],
                greeting_type=data["greeting_type"],
                include_audio=data["include_audio"],
            )
            return Response(GreetingResponseSerializer(result).data)
        except OpenAIConfigurationError as e:
            logger.error(f"OpenAI configuration error: {e}")
            return Response(
                {"error": "AIサービスが設定されていません"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AssistantError as e:
            logger.error(f"Assistant error: {e}")
            return Response(
                {"error": "挨拶の生成に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def _create_service(self) -> AssistantService:
        """AssistantServiceを作成."""
        return AssistantService(
            openai_client=OpenAIClient(),
            outlook_client=OutlookGraphClient(),
            weather_client=JMAWeatherClient(),
            tts_service_url=get_tts_service_url(),
        )


class GreetingAudioView(APIView):
    """挨拶音声生成API（WAVファイル直接返却）."""

    @extend_schema(
        request=GreetingRequestSerializer,
        responses={
            200: OpenApiResponse(
                description="WAV音声ファイル",
            ),
            404: OpenApiResponse(description="音声生成に失敗"),
        },
        description="今日の予定と天気を元に挨拶を生成し、WAV音声ファイルを返します",
        tags=["assistant"],
    )
    def post(self, request):
        """挨拶音声を生成してWAVファイルとして返却."""
        serializer = GreetingRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            service = self._create_service()
            result = service.generate_greeting(
                area_code=data["area_code"],
                greeting_type=data["greeting_type"],
                include_audio=True,  # 常に音声を生成
            )

            # data URI形式からバイナリに変換
            audio_data_uri = result.get("audio")
            if not audio_data_uri:
                return Response(
                    {"error": "音声の生成に失敗しました"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # data:audio/wav;base64,... から base64部分を抽出
            if audio_data_uri.startswith("data:audio/wav;base64,"):
                base64_data = audio_data_uri.replace("data:audio/wav;base64,", "")
                audio_bytes = base64.b64decode(base64_data)
            else:
                # base64のみの場合
                audio_bytes = base64.b64decode(audio_data_uri)

            response = HttpResponse(audio_bytes, content_type="audio/wav")
            response["Content-Disposition"] = 'attachment; filename="greeting.wav"'
            return response

        except OpenAIConfigurationError as e:
            logger.error(f"OpenAI configuration error: {e}")
            return Response(
                {"error": "AIサービスが設定されていません"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AssistantError as e:
            logger.error(f"Assistant error: {e}")
            return Response(
                {"error": "挨拶の生成に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def _create_service(self) -> AssistantService:
        """AssistantServiceを作成."""
        return AssistantService(
            openai_client=OpenAIClient(),
            outlook_client=OutlookGraphClient(),
            weather_client=JMAWeatherClient(),
            tts_service_url=get_tts_service_url(),
        )


class ChatView(APIView):
    """対話型チャットAPI."""

    @extend_schema(
        request=ChatRequestSerializer,
        responses={200: ChatResponseSerializer},
        description="ユーザーメッセージに対して回答を生成します（Function Calling対応）",
        tags=["assistant"],
    )
    def post(self, request):
        """チャット応答を生成."""
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            service = self._create_service()
            result = service.chat(
                message=data["message"],
                area_code=data.get("area_code"),
                include_audio=data["include_audio"],
            )
            return Response(ChatResponseSerializer(result).data)
        except OpenAIConfigurationError as e:
            logger.error(f"OpenAI configuration error: {e}")
            return Response(
                {"error": "AIサービスが設定されていません"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AssistantError as e:
            logger.error(f"Assistant error: {e}")
            return Response(
                {"error": "回答の生成に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def _create_service(self) -> AssistantService:
        """AssistantServiceを作成."""
        return AssistantService(
            openai_client=OpenAIClient(),
            outlook_client=OutlookGraphClient(),
            weather_client=JMAWeatherClient(),
            tts_service_url=get_tts_service_url(),
        )


class DailySummaryView(APIView):
    """日次サマリーAPI."""

    @extend_schema(
        parameters=[DailySummaryRequestSerializer],
        responses={200: DailySummaryResponseSerializer},
        description="1日の予定と天気のサマリーを生成します",
        tags=["assistant"],
    )
    def get(self, request):
        """日次サマリーを生成."""
        serializer = DailySummaryRequestSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            service = self._create_service()
            result = service.generate_daily_summary(
                area_code=data["area_code"],
                include_audio=data["include_audio"],
            )
            return Response(DailySummaryResponseSerializer(result).data)
        except OpenAIConfigurationError as e:
            logger.error(f"OpenAI configuration error: {e}")
            return Response(
                {"error": "AIサービスが設定されていません"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AssistantError as e:
            logger.error(f"Assistant error: {e}")
            return Response(
                {"error": "サマリーの生成に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def _create_service(self) -> AssistantService:
        """AssistantServiceを作成."""
        return AssistantService(
            openai_client=OpenAIClient(),
            outlook_client=OutlookGraphClient(),
            weather_client=JMAWeatherClient(),
            tts_service_url=get_tts_service_url(),
        )
