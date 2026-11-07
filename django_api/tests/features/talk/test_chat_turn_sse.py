"""チャットのターン（SSE モード）のテスト: イベントの順序と内容.

実行はモデルだけを差し替えて通す。失敗と切断は `test_chat_turn_failure.py`、
モードの切替と事前検証は `test_chat_turn_http.py`。
"""

from unittest.mock import patch

import pytest
from django.utils.dateparse import parse_datetime

from features.talk.models import ChatMessage, ChatSession
from features.talk.services import TalkService
from features.talk.views._sse import format_sse
from integrations.tts.client import TTSResult
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError
from tests.fixtures.llm import stream_of
from tests.fixtures.sse import (
    SEPARATE_DELTAS,
    audio_files,
    edit_sse,
    event_data,
    event_names,
    joined_deltas,
    parse_event,
    saved_messages,
    send_sse,
)

pytestmark = pytest.mark.usefixtures("chat_turn_env")


@pytest.mark.unit
class TestFormatSse:
    """format_sse のテスト."""

    def test_format_sse_uses_event_and_data_lines(self):
        assert format_sse("delta", {"text": "a"}) == (
            b'event: delta\ndata: {"text": "a"}\n\n'
        )

    def test_format_sse_keeps_non_ascii_as_utf8(self):
        chunk = format_sse("delta", {"text": "こんにちは"})

        assert chunk == 'event: delta\ndata: {"text": "こんにちは"}\n\n'.encode()

    def test_format_sse_escapes_newlines_in_one_data_line(self):
        chunk = format_sse("delta", {"text": "一行目\n二行目\r\n\n三行目"})

        event, data = parse_event(chunk)
        assert event == "delta"
        assert data == {"text": "一行目\n二行目\r\n\n三行目"}

    def test_format_sse_empty_data(self):
        assert format_sse("start", {}) == b"event: start\ndata: {}\n\n"


@pytest.mark.django_db
class TestEventSequence:
    """イベントの順序と内容."""

    def test_send_without_tts_emits_events_in_order(
        self, chat_llm, title_llm, auth_client, session
    ):
        """start → delta → message → title → done の順に流れる."""
        chat_llm.enqueue(stream_of("返", "信", gap=SEPARATE_DELTAS))
        title_llm.enqueue("生成タイトル")

        events = send_sse(auth_client, session.id).read_all()

        assert event_names(events) == ["start", "delta", "message", "title", "done"]
        assert [data for event, data in events if event == "delta"] == [
            {"text": "返"},
            {"text": "信"},
        ]
        assert event_data(events, "start") == {}
        assert event_data(events, "title") == {"title": "生成タイトル"}

    def test_send_with_tts_emits_audio_before_title(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session
    ):
        """音声は message の後、title の前に流れる."""
        chat_llm.enqueue("返信")
        title_llm.enqueue("生成タイトル")

        events = send_sse(auth_client, tts_session.id).read_all()

        assert event_names(events) == [
            "start",
            "delta",
            "message",
            "audio",
            "title",
            "done",
        ]

    def test_existing_title_emits_no_title_event(
        self, chat_llm, title_llm, auth_client, user, talk_setting
    ):
        """タイトルがあれば生成しない."""
        titled = ChatSession.objects.create(
            user=user, setting=talk_setting, title="既存"
        )
        chat_llm.enqueue("返信")

        events = send_sse(auth_client, titled.id).read_all()

        assert event_names(events) == ["start", "delta", "message", "done"]
        assert title_llm.requests == []

    def test_title_is_not_retried_past_opening_of_conversation(
        self, chat_llm, title_llm, auth_client, session
    ):
        """冒頭を過ぎたら題が空のままでも生成しない（失敗し続けても毎ターン呼ばない）."""
        for sequence, role in enumerate(["user", "assistant", "user", "assistant"]):
            ChatMessage.objects.create(
                session=session, sequence=sequence, role=role, content=f"#{sequence}"
            )
        chat_llm.enqueue("返信")

        events = send_sse(auth_client, session.id).read_all()

        assert event_names(events) == ["start", "delta", "message", "done"]
        assert title_llm.requests == []

    def test_deltas_concatenate_to_saved_reply(
        self, chat_llm, auth_client, session, title_llm
    ):
        """delta を連結したものが保存された本文と一致する."""
        chunks = ("一行目\n", "二行目 ", "<think>x</think>\n")
        chat_llm.enqueue(stream_of(*chunks, gap=SEPARATE_DELTAS))

        events = send_sse(auth_client, session.id).read_all()

        assert joined_deltas(events) == "".join(chunks)
        assert saved_messages(session) == [
            (0, "user", "おはよう"),
            (1, "assistant", "".join(chunks)),
        ]

    def test_message_event_has_saved_messages(
        self, chat_llm, title_llm, auth_client, session
    ):
        """message は保存されたメッセージの詳細を持つ."""
        chat_llm.enqueue("返信")

        events = send_sse(auth_client, session.id).read_all()

        message = event_data(events, "message")
        user_row = session.messages.get(role="user")
        assistant_row = session.messages.get(role="assistant")
        assert message["user"]["id"] == user_row.id
        assert message["user"]["sequence"] == 0
        assert message["user"]["role"] == "user"
        assert message["user"]["content"] == "おはよう"
        assert message["assistant"]["id"] == assistant_row.id
        assert message["assistant"]["sequence"] == 1
        assert message["assistant"]["role"] == "assistant"
        assert message["assistant"]["content"] == "返信"
        assert message["assistant"]["audio_url"] is None
        assert set(message["assistant"]) == {
            "id",
            "sequence",
            "role",
            "content",
            "audio_url",
            "audio_format",
            "audio_size_bytes",
            "created_at",
        }

    def test_done_event_has_session_summary(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session
    ):
        """done はセッションの最新の要約を持ち、updated_at を進める."""
        chat_llm.enqueue("返信")
        title_llm.enqueue("生成タイトル")
        before = tts_session.updated_at

        events = send_sse(auth_client, tts_session.id).read_all()

        done = event_data(events, "done")
        tts_session.refresh_from_db()
        assert set(done) == {
            "title",
            "message_count",
            "total_audio_bytes",
            "updated_at",
        }
        assert done["title"] == "生成タイトル"
        assert done["message_count"] == 2
        assert done["total_audio_bytes"] == 8
        assert parse_datetime(done["updated_at"]) == tts_session.updated_at
        assert tts_session.updated_at > before

    def test_done_advances_updated_at_after_commit(
        self, chat_llm, auth_client, user, talk_setting
    ):
        """done の時点でも updated_at を進める（タイトルも音声もないターンで確かめる）."""
        titled = ChatSession.objects.create(
            user=user, setting=talk_setting, title="既存"
        )
        chat_llm.enqueue("返信")
        reader = send_sse(auth_client, titled.id)

        reader.read_until("message")
        committed_at = ChatSession.objects.get(id=titled.id).updated_at
        events = reader.read_all()

        done_at = parse_datetime(event_data(events, "done")["updated_at"])
        assert done_at > committed_at

    def test_llm_receives_history_and_system_prompt(
        self, chat_llm, title_llm, auth_client, session, conversation
    ):
        """過去の履歴と今回の発話、system プロンプトを LLM に渡す."""
        chat_llm.enqueue("返信")

        send_sse(auth_client, session.id, "今の発話").read_all()

        request = chat_llm.requests[0]
        assert request.instructions == "あなたは親切な AI です。"
        assert request.conversation == [
            ("user", "#0"),
            ("assistant", "#1"),
            ("user", "#2"),
            ("assistant", "#3"),
            ("user", "今の発話"),
        ]

    def test_session_id_reaches_langfuse(
        self, chat_llm, title_llm, auth_client, session
    ):
        """チャットセッションの UUID を Langfuse のセッション ID にする."""
        chat_llm.enqueue("返信")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            send_sse(auth_client, session.id).read_all()

        mock_propagate.assert_any_call(session_id=str(session.id))

    @pytest.mark.parametrize(
        ("chunk", "stored"),
        [
            ("前\x00後", "前後"),
            ("前\ud83d後", "前?後"),
        ],
    )
    def test_text_that_cannot_be_stored_is_normalized(
        self, chunk, stored, chat_llm, title_llm, auth_client, session
    ):
        """NUL（PostgreSQL に保存できない）と孤立サロゲート（UTF-8 にできない）で応答を失わない."""
        chat_llm.enqueue(chunk)

        events = send_sse(auth_client, session.id).read_all()

        assert event_names(events)[-1] == "done"
        assert joined_deltas(events) == stored
        assert saved_messages(session)[1] == (1, "assistant", stored)

    @pytest.mark.parametrize(
        ("generated", "stored"),
        [
            ("題\x00名", "題名"),
            ("題\ud83d名", "題?名"),
        ],
    )
    def test_title_that_cannot_be_stored_is_normalized(
        self, generated, stored, chat_llm, title_llm, auth_client, session
    ):
        """タイトルも同じく正規化する."""
        chat_llm.enqueue("返信")
        title_llm.enqueue(generated)

        events = send_sse(auth_client, session.id).read_all()

        assert event_data(events, "title") == {"title": stored}
        session.refresh_from_db()
        assert session.title == stored

    def test_reply_without_text_saves_empty_assistant_and_skips_audio(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session
    ):
        """本文なしの応答は空の assistant として正常に終わり、音声は合成しない."""
        chat_llm.enqueue(stream_of())

        events = send_sse(auth_client, tts_session.id).read_all()

        assert event_names(events) == ["start", "message", "done"]
        assert saved_messages(tts_session) == [
            (0, "user", "おはよう"),
            (1, "assistant", ""),
        ]
        mock_tts.synthesize.assert_not_called()


@pytest.mark.django_db
class TestEdit:
    """編集再送の SSE."""

    def test_edit_replaces_target_and_later_messages(
        self,
        chat_llm,
        auth_client,
        session,
        conversation,
        django_capture_on_commit_callbacks,
    ):
        """対象以降を消して作り直し、前の履歴だけを LLM に渡す."""
        session.title = "既存"
        session.save()
        chat_llm.enqueue("再生成")
        removed = [conversation[3].audio_file.name]
        kept = conversation[1].audio_file.name
        storage = conversation[1].audio_file.storage

        with django_capture_on_commit_callbacks(execute=True):
            events = edit_sse(auth_client, session.id, conversation[2].id).read_all()

        assert event_names(events) == ["start", "delta", "message", "done"]
        assert chat_llm.requests[0].conversation == [
            ("user", "#0"),
            ("assistant", "#1"),
            ("user", "編集後"),
        ]
        assert saved_messages(session) == [
            (0, "user", "#0"),
            (1, "assistant", "#1"),
            (2, "user", "編集後"),
            (3, "assistant", "再生成"),
        ]
        message = event_data(events, "message")
        assert message["user"]["sequence"] == 2
        assert message["assistant"]["sequence"] == 3
        assert not storage.exists(removed[0])
        assert storage.exists(kept)

    def test_edit_target_deleted_during_llm_appends_to_end(
        self, chat_llm, auth_client, session, conversation
    ):
        """LLM の間に対象の行が消えていたら末尾に追加する."""
        session.title = "既存"
        session.save()
        chat_llm.enqueue(stream_of("再", "生成", gap=SEPARATE_DELTAS))
        reader = edit_sse(auth_client, session.id, conversation[2].id)

        reader.read_until("delta")
        conversation[2].delete()
        reader.read_all()

        assert saved_messages(session) == [
            (0, "user", "#0"),
            (1, "assistant", "#1"),
            (3, "assistant", "#3"),
            (4, "user", "編集後"),
            (5, "assistant", "再生成"),
        ]


@pytest.mark.django_db
class TestAudio:
    """音声合成のイベント."""

    def test_empty_audio_emits_audio_error_and_saves_no_file(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session, media_root
    ):
        """0 バイトの音声は成功として扱わない."""
        chat_llm.enqueue("返信")
        mock_tts.synthesize.return_value = TTSResult(
            audio_data=b"", content_type="audio/wav", format="wav"
        )

        events = send_sse(auth_client, tts_session.id).read_all()

        assert "audio" not in event_names(events)
        assert event_data(events, "audio_error")["error"] == "音声の合成に失敗しました"
        assert audio_files(media_root) == []
        assert tts_session.messages.get(role="assistant").content == "返信"

    def test_audio_event_has_saved_audio(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session, media_root
    ):
        """audio は保存した音声の情報を持つ."""
        chat_llm.enqueue("返信")

        events = send_sse(auth_client, tts_session.id).read_all()

        assistant = tts_session.messages.get(role="assistant")
        audio = event_data(events, "audio")
        assert audio == {
            "message_id": assistant.id,
            "audio_url": (
                f"http://testserver/talk/sessions/{tts_session.id}/audio/{assistant.id}/"
            ),
            "audio_format": "wav",
            "audio_size_bytes": 8,
        }
        assert assistant.audio_file.read() == b"\x00" * 8
        assert mock_tts.synthesize.call_args.kwargs["text"] == "返信"
        assert mock_tts.synthesize.call_args.kwargs["model"] == "model"

    @pytest.mark.parametrize(
        ("failure", "error"),
        [
            (TTSNetworkError("down"), "AI生成サービスへの接続に失敗しました"),
            (TTSTimeoutError("slow"), "サービスへのリクエストがタイムアウトしました"),
            (RuntimeError("unexpected"), "音声の合成に失敗しました"),
        ],
    )
    def test_audio_failure_emits_audio_error_and_continues(
        self, failure, error, chat_llm, title_llm, mock_tts, auth_client, tts_session
    ):
        """音声の失敗は致命にせず、本文を残して続行する."""
        chat_llm.enqueue("返信")
        title_llm.enqueue("生成タイトル")
        mock_tts.synthesize.side_effect = failure

        events = send_sse(auth_client, tts_session.id).read_all()

        assistant = tts_session.messages.get(role="assistant")
        assert event_names(events) == [
            "start",
            "delta",
            "message",
            "audio_error",
            "title",
            "done",
        ]
        assert event_data(events, "audio_error") == {
            "message_id": assistant.id,
            "error": error,
        }
        assert assistant.content == "返信"
        assert not assistant.audio_file

    def test_message_deleted_during_tts_leaves_no_file(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session, media_root
    ):
        """合成の間に行が消えたらファイルを残さず audio_error を送る."""
        chat_llm.enqueue("返信")

        def delete_rows_then_return(**kwargs):
            ChatMessage.objects.filter(session=tts_session).delete()
            return TTSResult(b"\x00" * 8, "audio/wav", "wav")

        mock_tts.synthesize.side_effect = delete_rows_then_return

        events = send_sse(auth_client, tts_session.id).read_all()

        assert "audio_error" in event_names(events)
        assert "audio" not in event_names(events)
        assert audio_files(media_root) == []

    def test_session_deleted_during_tts_emits_404_error(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session
    ):
        """合成の間にセッションごと消えたら 404 の error で終わる."""
        chat_llm.enqueue("返信")

        def delete_session_then_return(**kwargs):
            ChatSession.objects.filter(id=tts_session.id).delete()
            return TTSResult(b"\x00" * 8, "audio/wav", "wav")

        mock_tts.synthesize.side_effect = delete_session_then_return

        events = send_sse(auth_client, tts_session.id).read_all()

        assert event_names(events)[-1] == "error"
        assert event_data(events, "error")["status"] == 404
        assert title_llm.requests == []


@pytest.mark.django_db
class TestTitle:
    """タイトルの生成."""

    def test_title_failure_continues_to_done(self, chat_llm, auth_client, session):
        """タイトルの失敗では title を送らず、done まで流す."""
        chat_llm.enqueue("返信")

        with patch.object(
            TalkService, "generate_session_title", side_effect=RuntimeError("down")
        ):
            events = send_sse(auth_client, session.id).read_all()

        assert event_names(events) == ["start", "delta", "message", "done"]
        assert event_data(events, "done")["title"] == ""

    def test_empty_title_emits_no_title_event(
        self, chat_llm, title_llm, auth_client, session
    ):
        """生成結果が空なら title を送らない."""
        chat_llm.enqueue("返信")
        title_llm.enqueue("")

        events = send_sse(auth_client, session.id).read_all()

        assert event_names(events) == ["start", "delta", "message", "done"]

    def test_rename_during_llm_skips_title_generation(
        self, chat_llm, title_llm, auth_client, session
    ):
        """LLM の間に手動で名前を付けたら生成しない."""
        chat_llm.enqueue(stream_of("返", "信", gap=SEPARATE_DELTAS))
        reader = send_sse(auth_client, session.id)

        reader.read_until("delta")
        ChatSession.objects.filter(id=session.id).update(title="手動")
        events = reader.read_all()

        assert "title" not in event_names(events)
        assert title_llm.requests == []
        assert event_data(events, "done")["title"] == "手動"

    def test_generated_title_does_not_overwrite_manual_rename(
        self, chat_llm, auth_client, session
    ):
        """生成の間に手動で名前を付けても上書きしない."""
        chat_llm.enqueue("返信")

        def rename_then_generate(messages, *, session_id):
            ChatSession.objects.filter(id=session_id).update(title="手動")
            return "自動タイトル"

        with patch.object(
            TalkService, "generate_session_title", side_effect=rename_then_generate
        ):
            events = send_sse(auth_client, session.id).read_all()

        session.refresh_from_db()
        assert session.title == "手動"
        assert "title" not in event_names(events)
        assert event_data(events, "done")["title"] == "手動"

    def test_title_update_advances_updated_at(self, chat_llm, auth_client, session):
        """タイトルの更新でも updated_at を進める."""
        chat_llm.enqueue("返信")
        seen = {}

        def generate(messages, *, session_id):
            seen["before"] = ChatSession.objects.get(id=session_id).updated_at
            return "自動タイトル"

        with patch.object(TalkService, "generate_session_title", side_effect=generate):
            reader = send_sse(auth_client, session.id)
            reader.read_until("title")
            session.refresh_from_db()
            reader.disconnect()

        assert session.updated_at > seen["before"]
