"""チャットの 1 ターン（送信・編集再送）の実行.

LLM が完了または停止するまで DB に書かない（遅延コミット）。LLM の間はトランザクションも
ロックも持たず、失敗したら DB は変わらない（編集でも元の履歴と音声が残る）。

    prepare_turn         事前検証（失敗は通常の HTTP ステータスで返す）
    ChatTurnRunner       start → delta → commit_turn → message → audio → title → done
"""

import logging
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import status

from .models import ChatMessage, ChatSession, TalkSetting
from .serializers import ChatSessionMessageDetailSerializer, ChatTurnDoneSerializer
from .services import TalkService
from .views._common import (
    SESSION_MAX_MESSAGES,
    attach_audio_to_message,
    classify_synthesis_error,
    create_assistant_message,
)

logger = logging.getLogger(__name__)

TurnEvent = tuple[str, dict[str, Any]]

_SEND_FALLBACK = "チャット応答の生成中に問題が発生しました"
_EDIT_FALLBACK = "チャット応答の再生成中に問題が発生しました"
_AUDIO_FALLBACK = "音声の合成に失敗しました"
_AUDIO_SAVE_ERROR = "音声の保存に失敗しました"
_SESSION_GONE_ERROR = "セッションが見つかりません"
_NO_SETTING_ERROR = "このチャットには Talk 設定がないため、続けられません。新しいチャットを始めてください"
_DISABLED_SETTING_ERROR = (
    "このチャットの Talk 設定「{name}」は無効になっているため、続けられません。"
    "新しいチャットを始めてください"
)
_UNAVAILABLE_SCENE_ERROR = (
    "このチャットのシーン「{name}」は使えなくなったため、続けられません。"
    "新しいチャットを始めてください"
)
# タイトルを生成する履歴の上限。初回と、停止した初回ターン（最大 2 件）の次のターンまで
_TITLE_MAX_HISTORY = 2


class ChatTurnRejectedError(Exception):
    """事前検証でターンを拒否した（ビューが通常の HTTP 応答として返す）."""

    def __init__(self, status_code: int, payload: dict[str, Any]):
        super().__init__(payload)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class TurnPlan:
    """事前検証を通ったターンの実行に必要なもの.

    Attributes:
        session: 対象のセッション
        setting: セッションの Talk 設定
        content: 今回のユーザー発話
        history: 今回の発話より前の履歴（編集なら対象より前だけ）
        system_prompt: 展開済みの system プロンプト
        service: LLM と TTS を呼ぶサービス
        fallback_message: 想定外の例外のときにクライアントへ返すメッセージ
        edit_target_id: 編集対象のメッセージ ID（送信なら None）
    """

    session: ChatSession
    setting: TalkSetting
    content: str
    history: list[dict[str, str]]
    system_prompt: str
    service: TalkService
    fallback_message: str
    edit_target_id: int | None = None

    @property
    def conversation(self) -> list[dict[str, str]]:
        """LLM へ渡す会話（末尾が今回の発話）."""
        return [*self.history, {"role": "user", "content": self.content}]


def _usable_setting(session: ChatSession) -> TalkSetting:
    """セッションの Talk 設定とシーンが今も使えるかを確かめ、Talk 設定を返す.

    どれも作成時に固定するので、使えなくなったら（Talk 設定がない・無効・シーンが無効か
    設定から外れた）そのチャットは続けず、新しいチャットを促す。

    Raises:
        ChatTurnRejectedError: 使えない場合（400）
    """
    setting = session.setting
    if setting is None:
        raise ChatTurnRejectedError(
            status.HTTP_400_BAD_REQUEST,
            {"error": _NO_SETTING_ERROR},
        )
    if not setting.is_enabled:
        raise ChatTurnRejectedError(
            status.HTTP_400_BAD_REQUEST,
            {"error": _DISABLED_SETTING_ERROR.format(name=setting.name)},
        )
    skill = session.skill
    if skill is not None and not (
        skill.is_enabled and setting.skills.filter(pk=skill.pk).exists()
    ):
        raise ChatTurnRejectedError(
            status.HTTP_400_BAD_REQUEST,
            {"error": _UNAVAILABLE_SCENE_ERROR.format(name=skill.name)},
        )
    return setting


def prepare_turn(
    session: ChatSession,
    content: str,
    *,
    edit_target: ChatMessage | None = None,
) -> TurnPlan:
    """ターンの事前検証を行い、実行計画を返す.

    Talk 設定とシーン → 件数上限（送信のみ）→ LLM 設定 → プロンプト準備の順に確かめる。

    Args:
        session: 所有権を確認済みのセッション
        content: 検証済みのユーザー発話
        edit_target: 編集対象のメッセージ（送信なら None）

    Returns:
        ターンの実行計画

    Raises:
        ChatTurnRejectedError: 検証に失敗した場合
    """
    setting = _usable_setting(session)

    messages = session.messages.order_by("sequence")
    if edit_target is not None:
        messages = messages.filter(sequence__lt=edit_target.sequence)
    history = list(messages.values("role", "content"))
    if edit_target is None and len(history) >= SESSION_MAX_MESSAGES:
        raise ChatTurnRejectedError(
            status.HTTP_400_BAD_REQUEST,
            {
                "error": f"1 セッションのメッセージ数上限({SESSION_MAX_MESSAGES})に達しました"
            },
        )

    service = TalkService()
    fallback_message = _SEND_FALLBACK if edit_target is None else _EDIT_FALLBACK
    try:
        system_prompt = service.prepare_chat_prompt(setting, session.skill)
    except Exception as exc:
        status_code, error = classify_synthesis_error(exc, fallback_message)
        raise ChatTurnRejectedError(status_code, {"error": error}) from exc

    return TurnPlan(
        session=session,
        setting=setting,
        content=content,
        history=history,
        system_prompt=system_prompt,
        service=service,
        fallback_message=fallback_message,
        edit_target_id=None if edit_target is None else edit_target.id,
    )


def _claim_sequence(plan: TurnPlan) -> int:
    """今回の user メッセージの sequence を決める（ロックの中で呼ぶ）.

    編集なら対象以降を削除してその位置を使う。対象がすでに消えていたら末尾に追加する。
    """
    messages = ChatMessage.objects.filter(session_id=plan.session.id)
    if plan.edit_target_id is not None:
        target = messages.filter(id=plan.edit_target_id).first()
        if target is not None:
            # 個別に delete して post_delete シグナル（音声の物理削除）を確実に発火させる
            for old in messages.filter(sequence__gte=target.sequence).order_by(
                "-sequence"
            ):
                old.delete()
            return target.sequence
    last = messages.aggregate(last=Max("sequence"))["last"]
    return 0 if last is None else last + 1


def commit_turn(
    plan: TurnPlan, reply: str | None
) -> tuple[ChatMessage, ChatMessage | None]:
    """ターンの結果を短いトランザクションで保存する.

    セッションの行をロックしてから採番するので、同時送信でも一意制約は壊れない。

    Args:
        plan: ターンの実行計画
        reply: assistant の本文。None なら user だけを保存する

    Returns:
        (user メッセージ, assistant メッセージまたは None)

    Raises:
        ChatSession.DoesNotExist: セッションが削除済みの場合
    """
    session = plan.session
    with transaction.atomic():
        ChatSession.objects.select_for_update().get(id=session.id)
        sequence = _claim_sequence(plan)
        user_message = ChatMessage.objects.create(
            session=session, sequence=sequence, role="user", content=plan.content
        )
        assistant_message = None
        if reply is not None:
            assistant_message = create_assistant_message(
                session=session, sequence=sequence + 1, text=reply
            )
        ChatSession.objects.filter(id=session.id).update(updated_at=timezone.now())
    return user_message, assistant_message


def _storable_text(text: str) -> str:
    """LLM が生成した文字列を、保存と SSE の送信ができる形にする.

    PostgreSQL の text は NUL を保存できず、孤立サロゲートは UTF-8 にできない。1 文字の
    ために応答全体を失わないよう取り除く（ユーザー発話はシリアライザが拒否している）。
    """
    return text.replace("\x00", "").encode("utf-8", "replace").decode("utf-8")


def _close_quietly(stream: Iterator[str]) -> None:
    """LLM のストリームを閉じる（失敗で部分応答の保存を妨げないよう、ログだけ残す）."""
    try:
        stream.close()
    except Exception:
        logger.exception("LLM のストリームを閉じられませんでした")


class ChatTurnRunner:
    """1 ターンを実行し、進み具合をイベントの列にする.

    イベントの列を読み進めることで処理が進む。読むのをやめて `close()` すると
    停止・切断として扱い、それまでに届いた本文を保存する。

    Args:
        plan: ターンの実行計画
        request: `audio_url` を絶対 URL にするためのリクエスト
    """

    def __init__(self, plan: TurnPlan, *, request: Any = None):
        self._plan = plan
        self._serializer_context = {"request": request}

    def events(self) -> Iterator[TurnEvent]:
        """`(イベント名, データ)` を順に返す."""
        plan = self._plan
        try:
            reply = yield from self._stream_reply()
            user_message, assistant_message = commit_turn(plan, reply)
            yield (
                "message",
                {
                    "user": self._serialize(user_message),
                    "assistant": self._serialize(assistant_message),
                },
            )
            yield from self._audio_events(assistant_message)
            yield from self._title_events(reply)
            yield self._done_event()
        except ChatSession.DoesNotExist:
            logger.info("ターンの途中でセッションが削除された: %s", plan.session.id)
            yield (
                "error",
                {"status": status.HTTP_404_NOT_FOUND, "error": _SESSION_GONE_ERROR},
            )
        except Exception as exc:
            status_code, error = classify_synthesis_error(exc, plan.fallback_message)
            yield "error", {"status": status_code, "error": error}

    def _stream_reply(self) -> Generator[TurnEvent, None, str]:
        """LLM の応答を流し、本文を返す（停止・切断なら届いた分を保存して終わる）."""
        plan = self._plan
        parts: list[str] = []
        try:
            yield "start", {}
            stream = plan.service.stream_chat_reply(
                plan.system_prompt, plan.conversation, session_id=str(plan.session.id)
            )
            try:
                for text in map(_storable_text, stream):
                    parts.append(text)
                    yield "delta", {"text": text}
            finally:
                _close_quietly(stream)
        # GeneratorExit: 停止・切断で応答が閉じられた。本文がなくてもターンを確定する。
        # SystemExit: gunicorn がワーカーを強制終了する（--timeout の超過）。利用者の停止
        # ではないので、本文が届く前なら LLM の失敗と同じく何も保存しない。
        except GeneratorExit:
            self._save_stopped_turn("".join(parts))
            raise
        except SystemExit:
            if parts:
                self._save_stopped_turn("".join(parts))
            raise
        return "".join(parts)

    def _save_stopped_turn(self, partial_reply: str) -> None:
        """停止・切断されたターンを保存する（本文がなければ user だけ）.

        `close()` の中の例外は Django が握りつぶすので、ここでログに残す。
        """
        session_id = self._plan.session.id
        try:
            commit_turn(self._plan, partial_reply or None)
        except ChatSession.DoesNotExist:
            logger.info("停止したターンのセッションが削除済み: %s", session_id)
        except Exception:
            logger.exception("停止したターンの保存に失敗: %s", session_id)

    def _audio_events(self, message: ChatMessage) -> Iterator[TurnEvent]:
        """音声を合成して保存する（失敗は致命にしない）."""
        plan = self._plan
        tts_options = plan.setting.get_tts_options()
        if tts_options is None or not message.content.strip():
            return
        try:
            audio = plan.service.synthesize_audio(message.content, tts_options)
        except Exception as exc:
            _, error = classify_synthesis_error(exc, _AUDIO_FALLBACK)
            yield "audio_error", {"message_id": message.id, "error": error}
            return
        if not audio.audio_data:
            yield "audio_error", {"message_id": message.id, "error": _AUDIO_FALLBACK}
            return
        if not attach_audio_to_message(message, audio.audio_data, audio.format):
            yield "audio_error", {"message_id": message.id, "error": _AUDIO_SAVE_ERROR}
            return
        data = self._serialize(message)
        yield (
            "audio",
            {
                "message_id": message.id,
                "audio_url": data["audio_url"],
                "audio_format": data["audio_format"],
                "audio_size_bytes": data["audio_size_bytes"],
            },
        )

    def _title_events(self, reply: str) -> Iterator[TurnEvent]:
        """会話の冒頭でタイトルが空なら生成する（失敗しても続行し、手動の名前は上書きしない）.

        冒頭に限るのは、生成に失敗し続けるセッションで毎ターン LLM を呼ばないため。
        """
        plan = self._plan
        if len(plan.history) > _TITLE_MAX_HISTORY:
            return
        untitled = ChatSession.objects.filter(id=plan.session.id, title="")
        if not untitled.exists():
            return
        try:
            title = plan.service.generate_session_title(
                [*plan.conversation, {"role": "assistant", "content": reply}],
                session_id=str(plan.session.id),
            )
        except Exception:
            logger.exception("セッションタイトル生成に失敗")
            return
        title = _storable_text(title)
        if title and untitled.update(title=title, updated_at=timezone.now()):
            yield "title", {"title": title}

    def _done_event(self) -> TurnEvent:
        """セッションの更新日時を進め、最新の要約を返す."""
        sessions = ChatSession.objects.filter(id=self._plan.session.id)
        sessions.update(updated_at=timezone.now())
        return "done", dict(ChatTurnDoneSerializer(sessions.get()).data)

    def _serialize(self, message: ChatMessage) -> dict[str, Any]:
        serializer = ChatSessionMessageDetailSerializer(
            message, context=self._serializer_context
        )
        return dict(serializer.data)
