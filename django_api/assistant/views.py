"""アシスタントAPI ビュー."""

import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
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
