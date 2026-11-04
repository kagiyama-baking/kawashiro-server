"""Companion の実行 API（`POST /companion/run/`）."""

import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import authentication, permissions, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMTimeoutError,
)
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError

from .exceptions import (
    CompanionNotConfiguredError,
    PromptUnavailableError,
    UnknownSkillError,
)
from .serializers import CompanionRunRequestSerializer, CompanionRunResponseSerializer
from .services import run_companion
from .throttling import CompanionRateThrottle

logger = logging.getLogger(__name__)

# run_companion の既知の例外 → (HTTP ステータス, 応答のメッセージ)。上から順に照合する。
# LLMTimeoutError は LLMClientError のサブクラスなので、502 の行より前に置く
_KNOWN_ERRORS: tuple[tuple[tuple[type[Exception], ...], int, str], ...] = (
    (
        (CompanionNotConfiguredError, PromptUnavailableError, LLMConfigurationError),
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Companion の設定に問題があります",
    ),
    (
        (LLMTimeoutError,),
        status.HTTP_504_GATEWAY_TIMEOUT,
        "AI 生成サービスへのリクエストがタイムアウトしました",
    ),
    (
        (TTSTimeoutError,),
        status.HTTP_504_GATEWAY_TIMEOUT,
        "音声合成サービスへのリクエストがタイムアウトしました",
    ),
    (
        (LLMClientError,),
        status.HTTP_502_BAD_GATEWAY,
        "AI 生成サービスでエラーが発生しました",
    ),
    (
        (TTSNetworkError,),
        status.HTTP_502_BAD_GATEWAY,
        "音声合成サービスでエラーが発生しました",
    ),
)
_UNEXPECTED_ERROR = "セリフの生成中に問題が発生しました"


class CompanionRunView(APIView):
    """Companion の実行 API."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (CompanionRateThrottle,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["companion"],
        summary="発話に答えるセリフを生成（音声合成が有効なら音声も）",
        description="""有効な Companion 設定で、発話に答えるセリフを生成します。

設定は Django 管理画面の Companion 設定で、スキルの一覧は管理画面の Agent Skills で管理します（設定で使うスキルを選びます）。
システムプロンプトとスキルの本文は Langfuse で管理します。
エージェントは発話に合うスキルを選び、その手順に従って日時・天気・今日の予定をツールで取得して答えます。

## リクエストボディ

```json
{"prompt": "おはよう"}
```

`skill` を指定すると、エージェントに選ばせずにそのスキルを使います（スキルを読み込む往復がない分、速くなります）:

```json
{"prompt": "おはよう", "skill": "good-morning"}
```

## レスポンス

`skill` は使ったスキルの名前です（指定したスキル、指定がなければエージェントが読み込んだスキル。どちらもなければ null）。
音声合成が有効なら `audio_data` に Base64 でエンコードした音声が入ります。無効なら `audio_data` と `audio_format` は null です。

## 回数制限

1 ユーザーが 1 分間に実行できる回数に上限があります（管理画面の「回数の上限（1 分あたり）」、既定 10 回）。
超えると 429 を返し、`Retry-After` に次に実行できるまでの秒数が入ります。入力の不正や生成の失敗も 1 回と数えます。
""",
        request=CompanionRunRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=CompanionRunResponseSerializer,
                description="生成成功（音声合成が無効なら audio_data・audio_format は null）",
            ),
            400: OpenApiResponse(
                description=(
                    "入力が不正（項目ごとのエラー）、または指定したスキルが"
                    "有効な Companion 設定で選ばれていないか無効"
                )
            ),
            401: OpenApiResponse(description="認証エラー"),
            429: OpenApiResponse(
                description=(
                    "回数の上限（1 分あたり）を超えた。Retry-After 秒後に再試行"
                )
            ),
            500: OpenApiResponse(description="予期しないエラー"),
            502: OpenApiResponse(
                description="AI 生成サービス（応答の不正を含む）か音声合成サービスのエラー"
            ),
            503: OpenApiResponse(
                description=(
                    "有効な Companion 設定か、サービス設定（AI設定）の companion がない、"
                    "またはプロンプトの本文を取得できないか空"
                )
            ),
            504: OpenApiResponse(
                description="AI 生成サービスか音声合成サービスのタイムアウト"
            ),
        },
    )
    def post(self, request):
        """発話に答えるセリフを生成する."""
        serializer = CompanionRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reply = run_companion(
                serializer.validated_data["prompt"],
                skill=serializer.validated_data.get("skill"),
            )
        except UnknownSkillError as exc:
            logger.warning("Companion のスキルの指定が不正: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return _error_response(exc)
        return Response(CompanionRunResponseSerializer(reply).data)


def _error_response(exc: Exception) -> Response:
    """run_companion の例外を、決まったメッセージの応答にする（例外のメッセージは返さない）."""
    for error_types, status_code, message in _KNOWN_ERRORS:
        if isinstance(exc, error_types):
            logger.error(
                "Companion の実行に失敗しました（%s）: %s", type(exc).__name__, exc
            )
            return Response({"error": message}, status=status_code)
    logger.exception("Companion の実行中に予期しないエラーが発生しました", exc_info=exc)
    return Response(
        {"error": _UNEXPECTED_ERROR},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
