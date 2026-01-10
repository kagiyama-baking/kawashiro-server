"""Views for greeting app."""

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

from llm_client.exceptions import OpenAIAPIError, OpenAITimeoutError
from msgraph_config.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from tts.exceptions import TTSNetworkError, TTSTimeoutError
from weather.exceptions import (
    JMAAreaNotFoundError,
    JMANetworkError,
    JMAParseError,
    JMATimeoutError,
)

from .exceptions import HolidayNetworkError, HolidayTimeoutError
from .holiday_client import HolidayClient
from .models import EveningGreetingConfig, MorningGreetingConfig
from .serializers import (
    EveningGreetingResponseSerializer,
    MorningGreetingResponseSerializer,
    TodayInfoResponseSerializer,
)
from .services import EveningGreetingService, MorningGreetingService

logger = logging.getLogger(__name__)


def sanitize_for_header(text: str, max_length: int = 200) -> str:
    """HTTPヘッダー用にテキストをサニタイズ.

    制御文字を除去し、指定長に切り詰める。
    """
    # 制御文字（0x00-0x1F, 0x7F）を除去
    sanitized = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    return sanitized[:max_length]


class MorningGreetingView(APIView):
    """朝のあいさつAPI."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["greeting"],
        summary="朝のあいさつを生成",
        description="""朝のあいさつを生成します。

設定はDjango管理画面で事前に登録しておく必要があります。

## 処理フロー

1. 天気予報API（/weather/forecast/）から本日の天気を取得
2. 予定取得API（/outlook/events/）から本日の予定を取得
3. 日時情報（日付、曜日、祝日）を取得
4. OpenAI APIであいさつテキストを生成

## プレースホルダー

ユーザープロンプトで以下のプレースホルダーが使用可能です：

| プレースホルダー | 内容 |
|----------------|------|
| `{{datetime}}` | 日時情報（日付、曜日、祝日） |
| `{{weather}}` | 天気予報データ |
| `{{events}}` | 本日の予定データ |

### {{datetime}} の例

```json
{
  "date": "2025-01-11",
  "time": "09:30:00",
  "day_of_week": "Saturday",
  "day_of_week_ja": "土曜日",
  "holiday_name": null
}
```

### {{weather}} の例

```json
{
  "area_name": "東京都 東京地方",
  "area_code": "130010",
  "date": "2025-01-11",
  "weather": "晴れ　夜　くもり",
  "weather_code": "111",
  "temp_min": 4,
  "temp_max": 10,
  "pop_00_06": 10,
  "pop_06_12": 20,
  "pop_12_18": 30,
  "pop_18_24": 40
}
```

### {{events}} の例

```json
[
  {
    "subject": "チーム定例",
    "start": {"dateTime": "2025-01-11T10:00:00", "timeZone": "Tokyo Standard Time"},
    "end": {"dateTime": "2025-01-11T11:00:00", "timeZone": "Tokyo Standard Time"},
    "location": "会議室A",
    "is_all_day": false
  }
]
```

## 注意事項

- 予定がない場合、予定に関する言及はありません

## 音声合成

管理画面でTTSが有効になっている場合、音声データ（WAV形式）を直接返します。
TTS無効の場合はJSONでテキストのみ返します。
""",
        responses={
            200: OpenApiResponse(
                response=MorningGreetingResponseSerializer,
                description="あいさつ生成成功（JSON）",
            ),
            (200, "audio/wav"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ（WAV形式）- TTS有効時",
            ),
            401: OpenApiResponse(description="認証エラー"),
            404: OpenApiResponse(
                description="設定が見つからない / 予報区コードが見つからない"
            ),
            502: OpenApiResponse(description="外部APIへの接続エラー"),
            503: OpenApiResponse(description="サービス設定エラー"),
            504: OpenApiResponse(description="外部APIタイムアウト"),
        },
    )
    def get(self, request):
        """朝のあいさつを生成."""
        # 設定を取得
        config = MorningGreetingConfig.get_solo()
        if config is None:
            return Response(
                {"error": "朝のあいさつの設定が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            service = MorningGreetingService()
            result = service.generate_greeting(
                area_code=config.area_code,
                system_prompt=config.system_prompt,
                user_prompt=config.user_prompt,
                tts_options=config.get_tts_options(),
            )

            # 音声データがある場合はWAVを返す（HttpResponseを使用）
            if "audio_data" in result:
                audio_data = result["audio_data"]
                greeting_text = result["greeting_text"]
                response = HttpResponse(audio_data, content_type="audio/wav")
                response["Content-Disposition"] = 'attachment; filename="greeting.wav"'
                response["X-Greeting-Text"] = sanitize_for_header(greeting_text)
                return response

            # 音声なしの場合はJSONを返す
            response_serializer = MorningGreetingResponseSerializer(data=result)
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

        except (OpenAITimeoutError, TTSTimeoutError) as e:
            logger.error("AI/TTSサービスタイムアウト: %s", str(e))
            return Response(
                {"error": "AI生成サービスへのリクエストがタイムアウトしました"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        except (
            JMANetworkError,
            JMAParseError,
            NetworkError,
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


class EveningGreetingView(APIView):
    """夜のあいさつAPI."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["greeting"],
        summary="夜のあいさつを生成",
        description="""夜のあいさつを生成します。

設定はDjango管理画面で事前に登録しておく必要があります。

## 処理フロー

1. 日時情報（日付、曜日、祝日）を取得
2. OpenAI APIであいさつテキストを生成

## プレースホルダー

ユーザープロンプトで以下のプレースホルダーが使用可能です：

| プレースホルダー | 内容 |
|----------------|------|
| `{{datetime}}` | 日時情報（日付、曜日、祝日） |

### {{datetime}} の例

```json
{
  "date": "2025-01-11",
  "time": "21:30:00",
  "day_of_week": "Saturday",
  "day_of_week_ja": "土曜日",
  "holiday_name": null
}
```

## 音声合成

管理画面でTTSが有効になっている場合、音声データ（WAV形式）を直接返します。
TTS無効の場合はJSONでテキストのみ返します。
""",
        responses={
            200: OpenApiResponse(
                response=EveningGreetingResponseSerializer,
                description="あいさつ生成成功（JSON）",
            ),
            (200, "audio/wav"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="音声データ（WAV形式）- TTS有効時",
            ),
            401: OpenApiResponse(description="認証エラー"),
            404: OpenApiResponse(description="設定が見つからない"),
            502: OpenApiResponse(description="外部APIへの接続エラー"),
            504: OpenApiResponse(description="外部APIタイムアウト"),
        },
    )
    def get(self, request):
        """夜のあいさつを生成."""
        # 設定を取得
        config = EveningGreetingConfig.get_solo()
        if config is None:
            return Response(
                {"error": "夜のあいさつの設定が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            service = EveningGreetingService()
            result = service.generate_greeting(
                system_prompt=config.system_prompt,
                user_prompt=config.user_prompt,
                tts_options=config.get_tts_options(),
            )

            # 音声データがある場合はWAVを返す（HttpResponseを使用）
            if "audio_data" in result:
                audio_data = result["audio_data"]
                greeting_text = result["greeting_text"]
                response = HttpResponse(audio_data, content_type="audio/wav")
                response["Content-Disposition"] = 'attachment; filename="greeting.wav"'
                response["X-Greeting-Text"] = sanitize_for_header(greeting_text)
                return response

            # 音声なしの場合はJSONを返す
            response_serializer = EveningGreetingResponseSerializer(data=result)
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.data, status=status.HTTP_200_OK)

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

        except (OpenAITimeoutError, TTSTimeoutError) as e:
            logger.error("AI/TTSサービスタイムアウト: %s", str(e))
            return Response(
                {"error": "AI生成サービスへのリクエストがタイムアウトしました"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        except (OpenAIAPIError, TTSNetworkError) as e:
            logger.error("AI/TTSサービスエラー: %s", str(e))
            return Response(
                {"error": "AI生成サービスへの接続に失敗しました"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except Exception as e:
            logger.exception("予期しないエラー: %s", str(e))
            return Response(
                {"error": "あいさつの生成中に問題が発生しました"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# 曜日の日本語マッピング
DAY_OF_WEEK_JA = {
    "Monday": "月曜日",
    "Tuesday": "火曜日",
    "Wednesday": "水曜日",
    "Thursday": "木曜日",
    "Friday": "金曜日",
    "Saturday": "土曜日",
    "Sunday": "日曜日",
}


class TodayInfoView(APIView):
    """本日の日時情報API."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["greeting"],
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
