"""挨拶生成 / 設定一覧 / 日時情報 ビュー（既存 talk/synthesize 系）."""

import base64
import logging
from datetime import datetime

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import authentication, permissions, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from ..constants import DAY_OF_WEEK_JA
from ..exceptions import HolidayNetworkError, HolidayTimeoutError
from ..holiday_client import HolidayClient
from ..models import TalkConfig
from ..serializers import (
    ConfigListResponseSerializer,
    TalkRequestSerializer,
    TalkResponseSerializer,
    TodayInfoResponseSerializer,
)
from ..services import TalkService
from ._common import handle_synthesis_error

logger = logging.getLogger(__name__)


class TalkSynthesizeView(APIView):
    """会話生成API."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["talk"],
        summary="設定に基づき会話音声を生成",
        description="""指定した設定名に基づいて挨拶を生成します。

設定はDjango管理画面で事前に登録しておく必要があります。
システムプロンプトとユーザープロンプトは Langfuse で管理されます。

## リクエストボディ

```json
{
  "config_name": "morning"
}
```

`user_prompt` を指定すると Langfuse からの取得をスキップし、指定文字列を使用します:

```json
{
  "config_name": "morning",
  "user_prompt": "今日は {{datetime}} です。一言お願いします。"
}
```

## プレースホルダー（動的検出）

プロンプト文字列（システム/ユーザー両方）に以下のプレースホルダーを含めると、
対応するデータが自動的に取得・展開されます：

| プレースホルダー | 内容 | 追加設定 |
|----------------|------|----------|
| `{{datetime}}` | 日時情報（日付、曜日、祝日） | なし |
| `{{weather}}` | 天気予報データ | `config.area_code` 必須 |
| `{{events}}` | 本日の予定データ | Outlook 連携設定 |

`{{weather}}` 使用時に `area_code` が未設定の場合は 400 エラーが返ります。

## 音声合成

管理画面でTTSが有効になっている場合、音声データを直接返します（デフォルト: WAV形式）。
TTS無効の場合はJSONでテキストのみ返します。
""",
        request=TalkRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=TalkResponseSerializer,
                description="生成成功（TTS有効時はaudio_data含む）",
            ),
            400: OpenApiResponse(
                description=(
                    "リクエストパラメータ不正、またはプロンプトに含まれる "
                    "プレースホルダーに必要な設定が不足（例: {{weather}} + area_code 空）"
                )
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
    def post(self, request):
        """会話を生成."""
        request_serializer = TalkRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                request_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        config_name = request_serializer.validated_data["config_name"]
        user_prompt = request_serializer.validated_data.get("user_prompt")

        try:
            config = TalkConfig.objects.select_related(
                "system_prompt_ref", "user_prompt_ref"
            ).get(name=config_name)
        except TalkConfig.DoesNotExist:
            return Response(
                {"error": f"設定 '{config_name}' が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            service = TalkService()
            result = service.synthesize(config=config, user_prompt=user_prompt)

            if "audio_data" in result:
                response_data = {
                    "greeting_text": result["greeting_text"],
                    "audio_data": base64.b64encode(result["audio_data"]).decode(
                        "ascii"
                    ),
                    "audio_format": result.get("audio_format", "wav"),
                }
                response_serializer = TalkResponseSerializer(data=response_data)
                response_serializer.is_valid(raise_exception=True)
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            response_serializer = TalkResponseSerializer(data=result)
            response_serializer.is_valid(raise_exception=True)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return handle_synthesis_error(
                e,
                fallback_message="あいさつの生成中に問題が発生しました",
            )


class TodayInfoView(APIView):
    """本日の日時情報API."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["talk"],
        summary="本日の日時情報を取得",
        description="""本日の日時情報を取得します。

日本時間での日付、時刻、曜日、祝日情報を返します。
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
        tags=["talk"],
        summary="設定一覧を取得",
        description="登録されている会話生成設定の一覧を取得します。",
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
            configs = TalkConfig.objects.all().values(
                "name",
                "display_name",
                "tts_enabled",
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
