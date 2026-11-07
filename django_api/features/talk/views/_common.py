"""talk ビュー共通のヘルパ・例外マッピング."""

import logging

from django.core.files.base import ContentFile
from rest_framework import status

from integrations.langfuse.exceptions import PromptUnavailableError
from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMTimeoutError,
)
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError

from ..models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

# 1 セッションあたりのメッセージ件数上限（user + assistant 含む）。
# LLM コスト/レイテンシを抑える目的。
SESSION_MAX_MESSAGES = 50


def classify_synthesis_error(exc: Exception, fallback: str) -> tuple[int, str]:
    """チャットのターンの例外を HTTP ステータスとクライアント向けのメッセージに分類する.

    ターンで起きるのは LLM・TTS・プロンプトの準備の失敗だけ。HTTP の応答と SSE の
    `error` / `audio_error` イベントで共用する。ログもここで出す。

    Args:
        exc: 発生した例外
        fallback: 想定外の例外のときに返すメッセージ

    Returns:
        (HTTP ステータス, メッセージ)
    """
    # LLMTimeoutError は LLMClientError の子なので、接続の失敗より先に見る
    if isinstance(exc, (LLMTimeoutError, TTSTimeoutError)):
        logger.error("AI/TTSサービスタイムアウト: %s", str(exc))
        return (
            status.HTTP_504_GATEWAY_TIMEOUT,
            "サービスへのリクエストがタイムアウトしました",
        )

    if isinstance(exc, (LLMClientError, TTSNetworkError)):
        logger.error("AI/TTSサービスエラー: %s", str(exc))
        return status.HTTP_502_BAD_GATEWAY, "AI生成サービスへの接続に失敗しました"

    if isinstance(exc, (LLMConfigurationError, PromptUnavailableError)):
        logger.error("サービス設定エラー: %s", str(exc))
        return status.HTTP_503_SERVICE_UNAVAILABLE, "サービスの設定に問題があります"

    logger.error("予期しないエラー: %s", str(exc), exc_info=exc)
    return status.HTTP_500_INTERNAL_SERVER_ERROR, fallback


def get_owned_session(request, session_id) -> ChatSession | None:
    """request.user が所有する ChatSession を返す（無ければ None）.

    ターンの事前検証で使う Talk 設定（とシステムプロンプトの参照）とシーンも一緒に引く。
    """
    return (
        ChatSession.objects.select_related("setting__system_prompt_ref", "skill")
        .filter(id=session_id, user=request.user)
        .first()
    )


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
