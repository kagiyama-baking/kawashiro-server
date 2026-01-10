"""Views for greeting app."""

import logging
import re

from django.http import HttpResponse
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
from train.exceptions import (
    YahooNetworkError,
    YahooParseError,
    YahooRailNotFoundError,
    YahooTimeoutError,
)
from tts.exceptions import TTSNetworkError, TTSTimeoutError
from weather.exceptions import (
    JMAAreaNotFoundError,
    JMANetworkError,
    JMAParseError,
    JMATimeoutError,
)

from .models import MorningGreetingConfig
from .serializers import MorningGreetingResponseSerializer
from .services import MorningGreetingService

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
3. 路線運行情報API（/train/diainfo/）から運行情報を取得
4. OpenAI APIであいさつテキストを生成

## 注意事項

- 予定がない場合、予定に関する言及はありません
- 遅延がない場合、路線運行情報に関する言及はありません

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
                description="設定が見つからない / 予報区コードまたは路線IDが見つからない"
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
                rail_ids=config.get_rail_ids_list(),
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

        except YahooRailNotFoundError as e:
            logger.warning("路線IDが見つからない: %s", str(e))
            return Response(
                {"error": "指定された路線IDが見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        except (JMATimeoutError, YahooTimeoutError) as e:
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
            YahooNetworkError,
            YahooParseError,
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
