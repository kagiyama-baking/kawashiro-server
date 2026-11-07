"""talk ビュー共通のヘルパ・例外マッピング."""

import logging

from django.core.files.base import ContentFile
from rest_framework import status
from rest_framework.response import Response

from integrations.holiday import HolidayNetworkError, HolidayTimeoutError
from integrations.langfuse.exceptions import PromptUnavailableError
from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMTimeoutError,
)
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

from ..exceptions import PlaceholderDataMissingError
from ..models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

# 1 セッションあたりのメッセージ件数上限（user + assistant 含む）。
# LLM コスト/レイテンシを抑える目的。
SESSION_MAX_MESSAGES = 50


def classify_synthesis_error(exc: Exception, fallback: str) -> tuple[int, str]:
    """Talk 系の例外を HTTP ステータスとクライアント向けのメッセージに分類する.

    HTTP の応答と SSE の `error` イベントで共用する。ログもここで出す。

    Args:
        exc: 発生した例外
        fallback: 想定外の例外のときに返すメッセージ

    Returns:
        (HTTP ステータス, メッセージ)
    """
    if isinstance(exc, PlaceholderDataMissingError):
        logger.warning("プレースホルダー要求データ不足: %s", str(exc))
        return status.HTTP_400_BAD_REQUEST, str(exc)

    if isinstance(exc, WeatherAreaNotFoundError):
        logger.warning("予報区コードが見つからない: %s", str(exc))
        return status.HTTP_404_NOT_FOUND, "指定された予報区コードが見つかりません"

    if isinstance(exc, WeatherTimeoutError):
        logger.error("外部APIタイムアウト: %s", str(exc))
        return (
            status.HTTP_504_GATEWAY_TIMEOUT,
            "外部サービスへのリクエストがタイムアウトしました",
        )

    if isinstance(exc, (LLMTimeoutError, TTSTimeoutError, HolidayTimeoutError)):
        logger.error("AI/TTS/祝日サービスタイムアウト: %s", str(exc))
        return (
            status.HTTP_504_GATEWAY_TIMEOUT,
            "サービスへのリクエストがタイムアウトしました",
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
        return status.HTTP_502_BAD_GATEWAY, "外部サービスへの接続に失敗しました"

    if isinstance(exc, (LLMClientError, TTSNetworkError)):
        logger.error("AI/TTSサービスエラー: %s", str(exc))
        return status.HTTP_502_BAD_GATEWAY, "AI生成サービスへの接続に失敗しました"

    if isinstance(
        exc, (ConfigurationError, LLMConfigurationError, PromptUnavailableError)
    ):
        logger.error("サービス設定エラー: %s", str(exc))
        return status.HTTP_503_SERVICE_UNAVAILABLE, "サービスの設定に問題があります"

    if isinstance(exc, AuthenticationError):
        logger.error("外部サービス認証エラー: %s", str(exc))
        return status.HTTP_502_BAD_GATEWAY, "外部サービスへの認証に失敗しました"

    logger.error("予期しないエラー: %s", str(exc), exc_info=exc)
    return status.HTTP_500_INTERNAL_SERVER_ERROR, fallback


def handle_synthesis_error(exc: Exception, *, fallback_message: str) -> Response:
    """Talk 系ビュー共通の例外 → HTTP マッピング."""
    status_code, error = classify_synthesis_error(exc, fallback_message)
    return Response({"error": error}, status=status_code)


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
) -> bool:
    """生成済み ChatMessage に音声ファイルを保存する.

    DB トランザクションの外で呼ぶ（ロールバックでファイルだけが残らないように）。
    合成の間に行が削除されていたらファイルを残さない。失敗してもテキスト応答
    自体は残し、音声フィールドだけ未設定とする。

    Returns:
        保存できたら True、行が削除済みか保存に失敗したら False
    """
    saved = 0
    try:
        msg.audio_file.save(
            f"{msg.sequence}.{audio_format}",
            ContentFile(audio_data),
            save=False,
        )
        saved = ChatMessage.objects.filter(pk=msg.pk).update(
            audio_file=msg.audio_file.name,
            audio_format=audio_format,
            audio_size_bytes=len(audio_data),
        )
        if not saved:
            logger.info("音声の保存先の行が削除済み: message=%s", msg.pk)
    except Exception:
        logger.exception("音声ファイル保存に失敗（テキスト応答は維持）")
    if not saved:
        _discard_audio_file(msg)
        return False
    msg.audio_format = audio_format
    msg.audio_size_bytes = len(audio_data)
    return True


def _discard_audio_file(msg: ChatMessage) -> None:
    """行に紐付かなかった音声ファイルを消す（ファイルがなければ何もしない）."""
    if not msg.audio_file:
        return
    try:
        msg.audio_file.delete(save=False)
    except Exception:
        logger.exception("音声ファイルの削除に失敗: %s", msg.audio_file.name)
