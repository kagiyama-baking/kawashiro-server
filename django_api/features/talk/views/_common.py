"""talk ビュー共通のヘルパ・例外マッピング."""

import logging

from django.core.files.base import ContentFile
from rest_framework import status
from rest_framework.response import Response

from integrations.llm.exceptions import LLMClientError, LLMTimeoutError
from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError
from integrations.weather.exceptions import (
    WeatherAreaNotFoundError,
    WeatherNetworkError,
    WeatherParseError,
    WeatherTimeoutError,
)

from ..exceptions import (
    HolidayNetworkError,
    HolidayTimeoutError,
    PlaceholderDataMissingError,
)
from ..models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

# 1 セッションあたりのメッセージ件数上限（user + assistant 含む）。
# LLM コスト/レイテンシを抑える目的。
SESSION_MAX_MESSAGES = 50


def handle_synthesis_error(exc: Exception, *, fallback_message: str) -> Response:
    """Talk 系ビュー共通の例外 → HTTP マッピング."""
    if isinstance(exc, PlaceholderDataMissingError):
        logger.warning("プレースホルダー要求データ不足: %s", str(exc))
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(exc, WeatherAreaNotFoundError):
        logger.warning("予報区コードが見つからない: %s", str(exc))
        return Response(
            {"error": "指定された予報区コードが見つかりません"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, WeatherTimeoutError):
        logger.error("外部APIタイムアウト: %s", str(exc))
        return Response(
            {"error": "外部サービスへのリクエストがタイムアウトしました"},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    if isinstance(exc, (LLMTimeoutError, TTSTimeoutError, HolidayTimeoutError)):
        logger.error("AI/TTS/祝日サービスタイムアウト: %s", str(exc))
        return Response(
            {"error": "サービスへのリクエストがタイムアウトしました"},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    if isinstance(
        exc,
        (
            WeatherNetworkError,
            WeatherParseError,
            NetworkError,
            HolidayNetworkError,
        ),
    ):
        logger.error("外部API接続エラー: %s", str(exc))
        return Response(
            {"error": "外部サービスへの接続に失敗しました"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if isinstance(exc, (LLMClientError, TTSNetworkError)):
        logger.error("AI/TTSサービスエラー: %s", str(exc))
        return Response(
            {"error": "AI生成サービスへの接続に失敗しました"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if isinstance(exc, ConfigurationError):
        logger.error("サービス設定エラー: %s", str(exc))
        return Response(
            {"error": "サービスの設定に問題があります"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if isinstance(exc, AuthenticationError):
        logger.error("外部サービス認証エラー: %s", str(exc))
        return Response(
            {"error": "外部サービスへの認証に失敗しました"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    logger.exception("予期しないエラー: %s", str(exc))
    return Response(
        {"error": fallback_message},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def get_owned_session(request, session_id) -> ChatSession | None:
    """request.user が所有する ChatSession を返す（無ければ None）."""
    return ChatSession.objects.filter(id=session_id, user=request.user).first()


def create_assistant_message(
    session: ChatSession,
    sequence: int,
    text: str,
) -> ChatMessage:
    """assistant メッセージを DB に作成する（音声は別途）."""
    return ChatMessage.objects.create(
        session=session,
        sequence=sequence,
        role="assistant",
        content=text,
    )


def attach_audio_to_message(
    msg: ChatMessage,
    audio_data: bytes,
    audio_format: str,
) -> None:
    """生成済み ChatMessage に音声ファイルを保存する.

    DB トランザクション commit 後に呼ぶことを想定。失敗してもテキスト応答
    自体は残し、音声フィールドだけ未設定とする（オーファンファイル防止）。
    """
    try:
        msg.audio_file.save(
            f"{msg.sequence}.{audio_format}",
            ContentFile(audio_data),
            save=False,
        )
        msg.audio_format = audio_format
        msg.audio_size_bytes = len(audio_data)
        msg.save(update_fields=["audio_file", "audio_format", "audio_size_bytes"])
    except Exception:
        logger.exception("音声ファイル保存に失敗（テキスト応答は維持）")
