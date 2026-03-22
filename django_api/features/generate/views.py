"""Views for generate app."""

import logging
import re
from datetime import datetime

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import authentication, permissions, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.llm.exceptions import OpenAIAPIError, OpenAITimeoutError
from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError
from integrations.weather.exceptions import (
    JMAAreaNotFoundError,
    JMANetworkError,
    JMAParseError,
    JMATimeoutError,
)

from .constants import DAY_OF_WEEK_JA
from .exceptions import HolidayNetworkError, HolidayTimeoutError
from .holiday_client import HolidayClient
from .models import GreetingConfig
from .serializers import (
    ConfigListResponseSerializer,
    GreetingRequestSerializer,
    GreetingResponseSerializer,
    TodayInfoResponseSerializer,
)
from .services import GreetingService

logger = logging.getLogger(__name__)

# 音声フォーマットのホワイトリスト
ALLOWED_AUDIO_FORMATS = {"wav", "mp3", "ogg"}


def sanitize_for_header(text: str, max_length: int = 200) -> str:
    """HTTPヘッダー用にテキストをサニタイズ.

    制御文字を除去し、指定長に切り詰める。
    """
    # 制御文字（0x00-0x1F, 0x7F）を除去
    sanitized = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    return sanitized[:max_length]


class GreetingView(APIView):
    """挨拶生成API."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["generate"],
        summary="挨拶を生成",
        description="""指定した設定名に基づいて挨拶を生成します。

設定はDjango管理画面で事前に登録しておく必要があります。

## リクエストボディ

```json
{
  "config_name": "morning",
  "user_prompt": "{{weather}}の情報と{{events}}の予定を踏まえて、朝のあいさつをしてください。今日は{{datetime}}です。"
}
```

## プレースホルダー

ユーザープロンプトで以下のプレースホルダーが使用可能です（設定で有効化されている場合）：

| プレースホルダー | 内容 |
|----------------|------|
| `{{datetime}}` | 日時情報（日付、曜日、祝日） |
| `{{weather}}` | 天気予報データ |
| `{{events}}` | 本日の予定データ |

## 音声合成

管理画面でTTSが有効になっている場合、音声データを直接返します（デフォルト: WAV形式）。
TTS無効の場合はJSONでテキストのみ返します。
""",
        request=GreetingRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=GreetingResponseSerializer,
                description="あいさつ生成成功（JSON）",
            ),
            (200, "audio/wav"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ（WAV形式）- TTS有効時（デフォルト）",
            ),
            (200, "audio/mpeg"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ（MP3形式）- TTS有効時",
            ),
            (200, "audio/ogg"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ（OGG形式）- TTS有効時",
            ),
            400: OpenApiResponse(description="リクエストパラメータ不正"),
            401: OpenApiResponse(description="認証エラー"),
            404: OpenApiResponse(
                description="設定が見つからない / 予報区コードが見つからない"
            ),
            502: OpenApiResponse(description="外部APIへの接続エラー"),
            503: OpenApiResponse(description="サービス設定エラー"),
            504: OpenApiResponse(description="外部APIタイムアウト"),
        },
    )
    def post(self, request):
        """挨拶を生成."""
        # リクエストをバリデーション
        request_serializer = GreetingRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                request_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        config_name = request_serializer.validated_data["config_name"]
        user_prompt = request_serializer.validated_data["user_prompt"]

        # 設定を取得
        try:
            config = GreetingConfig.objects.get(name=config_name)
        except GreetingConfig.DoesNotExist:
            return Response(
                {"error": f"設定 '{config_name}' が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            service = GreetingService()
            result = service.generate_greeting(
                config=config,
                user_prompt=user_prompt,
            )

            # 音声データがある場合は音声を返す（HttpResponseを使用）
            if "audio_data" in result:
                audio_data = result["audio_data"]
                greeting_text = result["greeting_text"]
                audio_format = result.get("audio_format", "wav")
                # ホワイトリスト検証: 不正な値はデフォルトにフォールバック
                if audio_format not in ALLOWED_AUDIO_FORMATS:
                    audio_format = "wav"
                content_type_map = {
                    "wav": "audio/wav",
                    "mp3": "audio/mpeg",
                    "ogg": "audio/ogg",
                }
                content_type = content_type_map[audio_format]
                response = HttpResponse(audio_data, content_type=content_type)
                response["Content-Disposition"] = (
                    f'attachment; filename="greeting.{audio_format}"'
                )
                response["X-Generate-Text"] = sanitize_for_header(greeting_text)
                return response

            # 音声なしの場合はJSONを返す
            response_serializer = GreetingResponseSerializer(data=result)
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except JMAAreaNotFoundError as e:
            logger.warning("予報区コードが見つからない: %s", str(e))
            return Response(
                {"error": "指定された予報区コードが見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        except JMATimeoutError as e:
            logger.error("外部APIタイムアウト: %s", str(e))
            return Response(
                {"error": "外部サービスへのリクエストがタイムアウトしました"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        except (OpenAITimeoutError, TTSTimeoutError, HolidayTimeoutError) as e:
            logger.error("AI/TTS/祝日サービスタイムアウト: %s", str(e))
            return Response(
                {"error": "サービスへのリクエストがタイムアウトしました"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        except (
            JMANetworkError,
            JMAParseError,
            NetworkError,
            HolidayNetworkError,
        ) as e:
            logger.error("外部API接続エラー: %s", str(e))
            return Response(
                {"error": "外部サービスへの接続に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except (OpenAIAPIError, TTSNetworkError) as e:
            logger.error("AI/TTSサービスエラー: %s", str(e))
            return Response(
                {"error": "AI生成サービスへの接続に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except ConfigurationError as e:
            logger.error("サービス設定エラー: %s", str(e))
            return Response(
                {"error": "サービスの設定に問題があります"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except AuthenticationError as e:
            logger.error("外部サービス認証エラー: %s", str(e))
            return Response(
                {"error": "外部サービスへの認証に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except Exception as e:
            logger.exception("予期しないエラー: %s", str(e))
            return Response(
                {"error": "あいさつの生成中に問題が発生しました"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TodayInfoView(APIView):
    """本日の日時情報API."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["generate"],
        summary="本日の日時情報を取得",
        description="""本日の日時情報を取得します。

日本時間での日付、時刻、曜日、祝日情報を返します。

## レスポンス例

```json
{
    "date": "2025-01-11",
    "time": "09:30:00",
    "day_of_week": "Saturday",
    "day_of_week_ja": "土曜日",
    "holiday_name": null
}
```

祝日の場合:

```json
{
    "date": "2025-01-01",
    "time": "08:00:00",
    "day_of_week": "Wednesday",
    "day_of_week_ja": "水曜日",
    "holiday_name": "元日"
}
```
""",
        responses={
            200: OpenApiResponse(
                response=TodayInfoResponseSerializer,
                description="日時情報取得成功",
            ),
            401: OpenApiResponse(description="認証エラー"),
            502: OpenApiResponse(description="祝日APIへの接続エラー"),
            504: OpenApiResponse(description="祝日APIタイムアウト"),
        },
    )
    def get(self, request):
        """本日の日時情報を取得."""
        try:
            now = datetime.now(timezone.get_current_timezone())
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            day_of_week = now.strftime("%A")
            day_of_week_ja = DAY_OF_WEEK_JA.get(day_of_week, day_of_week)

            # 祝日を取得
            holiday_client = HolidayClient()
            holiday_name = holiday_client.get_holiday_name(date_str)

            data = {
                "date": date_str,
                "time": time_str,
                "day_of_week": day_of_week,
                "day_of_week_ja": day_of_week_ja,
                "holiday_name": holiday_name,
            }

            serializer = TodayInfoResponseSerializer(data=data)
            serializer.is_valid(raise_exception=True)

            return Response(serializer.data, status=status.HTTP_200_OK)

        except HolidayTimeoutError as e:
            logger.error("祝日APIタイムアウト: %s", str(e))
            return Response(
                {"error": "祝日APIへのリクエストがタイムアウトしました"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        except HolidayNetworkError as e:
            logger.error("祝日API接続エラー: %s", str(e))
            return Response(
                {"error": "祝日APIへの接続に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except Exception as e:
            logger.exception("予期しないエラー: %s", str(e))
            return Response(
                {"error": "日時情報の取得中に問題が発生しました"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ConfigsListView(APIView):
    """設定一覧API."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["generate"],
        summary="設定一覧を取得",
        description="登録されているテキスト生成設定の一覧を取得します。",
        responses={
            200: OpenApiResponse(
                response=ConfigListResponseSerializer,
                description="設定一覧取得成功",
            ),
            401: OpenApiResponse(description="認証エラー"),
        },
    )
    def get(self, request):
        """設定一覧を取得."""
        try:
            configs = GreetingConfig.objects.all().values(
                "name",
                "display_name",
                "tts_enabled",
                "use_weather",
                "use_events",
                "use_datetime",
            )
            serializer = ConfigListResponseSerializer(data={"configs": list(configs)})
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("設定一覧取得中の予期しないエラー: %s", str(e))
            return Response(
                {"error": "設定一覧の取得中に問題が発生しました"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
