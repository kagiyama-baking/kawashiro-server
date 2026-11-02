"""チャットのターンのテスト: LLM の失敗・停止と切断・遅延コミット.

切断は `response.close()` で再現する（WSGI サーバーが書き込みの失敗で応答を閉じるのと同じ経路。
Django テストクライアントの `closing_iterator_wrapper` を通る）。
"""

from unittest.mock import patch

import pytest
from django.db import connection
from pydantic_ai.exceptions import ModelHTTPError, ModelTimeoutError
from pydantic_ai.models.function import AgentInfo, FunctionModel

from features.talk.chat_turn import commit_turn, prepare_turn
from features.talk.llm_agents import TALK_CHAT_AGENT
from features.talk.models import ChatMessage, ChatSession
from features.talk.services import TalkService
from tests.fixtures.llm import stream_of
from tests.fixtures.sse import (
    SEPARATE_DELTAS,
    audio_files,
    edit_sse,
    event_data,
    event_names,
    joined_deltas,
    saved_messages,
    send_sse,
    send_url,
)

pytestmark = pytest.mark.usefixtures("chat_turn_env")


def _prepare_plan(session, edit_target=None):
    """プロンプトの準備を飛ばして実行計画を作る."""
    with patch.object(TalkService, "prepare_chat_prompt", return_value="s"):
        return prepare_turn(session, "今の発話", edit_target=edit_target)


@pytest.mark.django_db
class TestLLMFailure:
    """LLM の失敗: error を送って終わり、DB は変わらない."""

    def test_failure_before_first_delta_emits_error(
        self, chat_llm, auth_client, session
    ):
        """本文が届く前の失敗."""
        chat_llm.enqueue(ModelHTTPError(500, "test-alias"))

        events = send_sse(auth_client, session.id).read_all()

        assert event_names(events) == ["start", "error"]
        assert event_data(events, "error") == {
            "status": 502,
            "error": "AI生成サービスへの接続に失敗しました",
        }
        assert session.messages.count() == 0

    def test_failure_midway_saves_nothing(self, chat_llm, auth_client, session):
        """本文の途中の失敗でも user を含めて保存しない."""
        chat_llm.enqueue(
            stream_of(
                "途中",
                "続き",
                gap=SEPARATE_DELTAS,
                raises=ModelHTTPError(500, "test-alias"),
            )
        )

        events = send_sse(auth_client, session.id).read_all()

        assert event_names(events)[:2] == ["start", "delta"]
        assert event_names(events)[-1] == "error"
        assert session.messages.count() == 0
        session.refresh_from_db()
        assert session.title == ""

    def test_timeout_is_reported_as_504(self, chat_llm, auth_client, session):
        """タイムアウトは status 504 の error になる."""
        chat_llm.enqueue(ModelTimeoutError("test-alias", "timeout"))

        events = send_sse(auth_client, session.id).read_all()

        assert event_data(events, "error")["status"] == 504

    def test_edit_failure_keeps_history_and_audio(
        self, chat_llm, auth_client, session, conversation
    ):
        """編集の途中で失敗しても元の履歴と音声が残る（音声だけ消える不具合の解消）."""
        chat_llm.enqueue(
            stream_of(
                "途中",
                "続き",
                gap=SEPARATE_DELTAS,
                raises=ModelHTTPError(500, "test-alias"),
            )
        )
        audio_names = [conversation[1].audio_file.name, conversation[3].audio_file.name]
        storage = conversation[1].audio_file.storage

        events = edit_sse(auth_client, session.id, conversation[0].id).read_all()

        assert event_names(events)[-1] == "error"
        assert saved_messages(session) == [
            (0, "user", "#0"),
            (1, "assistant", "#1"),
            (2, "user", "#2"),
            (3, "assistant", "#3"),
        ]
        assert all(storage.exists(name) for name in audio_names)

    def test_commit_failure_emits_error(self, chat_llm, auth_client, session):
        """応答の後で保存に失敗したら error を送る."""
        chat_llm.enqueue("返信")

        with patch(
            "features.talk.chat_turn.commit_turn", side_effect=RuntimeError("db down")
        ):
            events = send_sse(auth_client, session.id).read_all()

        assert event_names(events) == ["start", "delta", "error"]
        assert event_data(events, "error") == {
            "status": 500,
            "error": "チャット応答の生成中に問題が発生しました",
        }

    def test_session_deleted_during_llm_emits_404_error(
        self, chat_llm, auth_client, session
    ):
        """LLM の間にセッションが消えたら 404 の error を送り、何も作らない."""
        chat_llm.enqueue(stream_of("途", "中", gap=SEPARATE_DELTAS))
        reader = send_sse(auth_client, session.id)

        reader.read_until("delta")
        session_id = session.id
        session.delete()
        events = reader.read_all()

        assert event_names(events)[-1] == "error"
        assert event_data(events, "error")["status"] == 404
        assert not ChatMessage.objects.filter(session_id=session_id).exists()


@pytest.mark.django_db
class TestDisconnect:
    """停止・切断: user と部分応答を保存する（音声とタイトルは実行しない）."""

    def test_disconnect_midway_saves_user_and_partial(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session, media_root
    ):
        """本文の途中で切れたら届いた分を保存する."""
        chat_llm.enqueue(stream_of("途中まで", hang=True))
        reader = send_sse(auth_client, tts_session.id)

        events = reader.read_until("delta")
        reader.disconnect()

        assert joined_deltas(events) == "途中まで"
        assert saved_messages(tts_session) == [
            (0, "user", "おはよう"),
            (1, "assistant", "途中まで"),
        ]
        mock_tts.synthesize.assert_not_called()
        assert title_llm.requests == []
        assert audio_files(media_root) == []

    def test_disconnect_before_text_saves_user_only(
        self, chat_llm, title_llm, auth_client, session
    ):
        """本文が届く前に切れたら user だけ保存する."""
        chat_llm.enqueue(stream_of(hang=True))
        reader = send_sse(auth_client, session.id)

        assert reader.next_event() == ("start", {})
        reader.disconnect()

        assert saved_messages(session) == [(0, "user", "おはよう")]
        assert chat_llm.requests == []

    def test_disconnect_before_first_read_saves_nothing(
        self, chat_llm, auth_client, session
    ):
        """1 バイトも読まずに閉じたら（ターンが始まっていないので）何もしない."""
        chat_llm.enqueue("返信")
        reader = send_sse(auth_client, session.id)

        reader.disconnect()

        assert session.messages.count() == 0
        assert chat_llm.requests == []

    def test_disconnect_advances_updated_at(
        self, chat_llm, title_llm, auth_client, session
    ):
        """切断でもセッションの更新日時を進める（一覧の並びに反映する）."""
        chat_llm.enqueue(stream_of("途中", hang=True))
        before = session.updated_at
        reader = send_sse(auth_client, session.id)

        reader.read_until("delta")
        reader.disconnect()

        session.refresh_from_db()
        assert session.updated_at > before

    def test_edit_disconnect_replaces_target_and_later(
        self, chat_llm, auth_client, session, conversation
    ):
        """編集の切断は対象以降を置き換え、古い音声を消す."""
        chat_llm.enqueue(stream_of("途中", hang=True))
        removed = conversation[3].audio_file.name
        storage = conversation[3].audio_file.storage
        reader = edit_sse(auth_client, session.id, conversation[2].id)

        reader.read_until("delta")
        reader.disconnect()

        assert saved_messages(session) == [
            (0, "user", "#0"),
            (1, "assistant", "#1"),
            (2, "user", "編集後"),
            (3, "assistant", "途中"),
        ]
        assert not storage.exists(removed)

    def test_edit_disconnect_before_text_keeps_user_only(
        self, chat_llm, auth_client, session, conversation
    ):
        """編集で本文が届く前に切れたら、新しい user だけを残す."""
        chat_llm.enqueue(stream_of(hang=True))
        reader = edit_sse(auth_client, session.id, conversation[2].id)

        reader.next_event()
        reader.disconnect()

        assert saved_messages(session) == [
            (0, "user", "#0"),
            (1, "assistant", "#1"),
            (2, "user", "編集後"),
        ]

    def test_disconnect_with_session_deleted_does_nothing(
        self, chat_llm, auth_client, session
    ):
        """切断の時点でセッションが消えていても例外にしない."""
        chat_llm.enqueue(stream_of("途中", hang=True))
        reader = send_sse(auth_client, session.id)

        reader.read_until("delta")
        session_id = session.id
        session.delete()
        reader.disconnect()

        assert not ChatMessage.objects.filter(session_id=session_id).exists()

    def test_commit_failure_on_disconnect_is_logged(
        self, chat_llm, auth_client, session, caplog
    ):
        """close() の中の例外は Django が握りつぶすので、自分でログに残す."""
        chat_llm.enqueue(stream_of("途中", hang=True))
        reader = send_sse(auth_client, session.id)
        reader.read_until("delta")

        with patch(
            "features.talk.chat_turn.commit_turn", side_effect=RuntimeError("db down")
        ):
            reader.disconnect()

        records = [
            record
            for record in caplog.records
            if record.name == "features.talk.chat_turn" and record.levelname == "ERROR"
        ]
        assert len(records) == 1
        assert records[0].exc_info is not None

    def test_llm_stream_close_failure_still_saves_partial(
        self, chat_llm, auth_client, session, caplog
    ):
        """LLM のストリームを閉じるときの失敗でも部分応答を失わない."""

        class FailingStream:
            def __iter__(self):
                return self

            def __next__(self):
                return "途中"

            def close(self):
                raise RuntimeError("close failed")

        with patch.object(
            TalkService, "stream_chat_reply", return_value=FailingStream()
        ):
            reader = send_sse(auth_client, session.id)
            reader.read_until("delta")
            reader.disconnect()

        assert saved_messages(session) == [
            (0, "user", "おはよう"),
            (1, "assistant", "途中"),
        ]
        records = [
            record
            for record in caplog.records
            if record.name == "features.talk.chat_turn" and record.levelname == "ERROR"
        ]
        assert len(records) == 1
        assert str(records[0].exc_info[1]) == "close failed"

    def test_disconnect_after_message_keeps_reply_and_skips_rest(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session
    ):
        """本文の保存後に切れたら二重に保存せず、音声とタイトルは実行しない."""
        chat_llm.enqueue("返信")
        reader = send_sse(auth_client, tts_session.id)

        reader.read_until("message")
        reader.disconnect()

        assert saved_messages(tts_session) == [
            (0, "user", "おはよう"),
            (1, "assistant", "返信"),
        ]
        mock_tts.synthesize.assert_not_called()
        assert title_llm.requests == []

    def test_disconnect_after_audio_keeps_audio(
        self, chat_llm, title_llm, mock_tts, auth_client, tts_session
    ):
        """音声の保存後に切れても音声は残り、タイトルは実行しない."""
        chat_llm.enqueue("返信")
        reader = send_sse(auth_client, tts_session.id)

        reader.read_until("audio")
        reader.disconnect()

        assistant = tts_session.messages.get(role="assistant")
        assert assistant.audio_file
        assert assistant.audio_size_bytes == 8
        assert title_llm.requests == []

    def test_next_turn_after_stopped_first_turn_generates_title(
        self, chat_llm, title_llm, auth_client, session
    ):
        """停止した初回ターンの救済: 次のターンでタイトルを作る（履歴の先頭から）."""
        chat_llm.enqueue(stream_of("途中", hang=True), "次の返信")
        title_llm.enqueue("救済タイトル")
        reader = send_sse(auth_client, session.id, "最初の発話")
        reader.read_until("delta")
        reader.disconnect()

        events = send_sse(auth_client, session.id, "次の発話").read_all()

        assert event_data(events, "title") == {"title": "救済タイトル"}
        session.refresh_from_db()
        assert session.title == "救済タイトル"
        assert title_llm.requests[0].user_prompt == (
            "user: 最初の発話\nassistant: 途中\nuser: 次の発話\nassistant: 次の返信"
        )
        assert chat_llm.requests[1].conversation == [
            ("user", "最初の発話"),
            ("assistant", "途中"),
            ("user", "次の発話"),
        ]


@pytest.mark.django_db(transaction=True)
class TestNoTransactionDuringLLM:
    """LLM の間はトランザクションを持たない（ロックで他のリクエストを待たせない）."""

    @pytest.fixture
    def llm_transaction_state(self, talk_llm_settings):
        seen: list[bool] = []

        async def stream(messages, info: AgentInfo):
            seen.append(connection.in_atomic_block)
            yield "返信"

        with TALK_CHAT_AGENT.override(model=FunctionModel(stream_function=stream)):
            yield seen

    def test_sse_mode_runs_llm_outside_transaction(
        self, llm_transaction_state, auth_client, session
    ):
        send_sse(auth_client, session.id).read_all()

        assert llm_transaction_state == [False]
        assert session.messages.count() == 2

    def test_json_mode_runs_llm_outside_transaction(
        self, llm_transaction_state, auth_client, session
    ):
        response = auth_client.post(
            send_url(session.id), {"content": "hi"}, format="json"
        )

        assert response.status_code == 201
        assert llm_transaction_state == [False]


@pytest.mark.django_db
class TestConcurrentTurns:
    """同時送信: コミット時に採番するので一意制約は壊れない."""

    def test_turns_prepared_together_get_distinct_sequences(
        self, chat_llm, title_llm, auth_client, session
    ):
        """同じ履歴を見て始めたターンも、コミットの順に採番される."""
        chat_llm.enqueue("一番目", "二番目")
        first = send_sse(auth_client, session.id, "A")
        second = send_sse(auth_client, session.id, "B")

        first_events = first.read_all()
        second_events = second.read_all()

        assert event_data(first_events, "message")["user"]["sequence"] == 0
        assert event_data(second_events, "message")["user"]["sequence"] == 2
        assert saved_messages(session) == [
            (0, "user", "A"),
            (1, "assistant", "一番目"),
            (2, "user", "B"),
            (3, "assistant", "二番目"),
        ]

    def test_interleaved_streams_do_not_collide(
        self, chat_llm, title_llm, auth_client, session
    ):
        """応答の途中で別のターンが割り込んでも衝突しない（文脈がずれるだけ）."""
        chat_llm.enqueue(stream_of("先", "発", gap=SEPARATE_DELTAS), "後発")
        first = send_sse(auth_client, session.id, "A")
        first.read_until("delta")

        second_events = send_sse(auth_client, session.id, "B").read_all()
        first_events = first.read_all()

        assert event_names(second_events)[-1] == "done"
        assert event_names(first_events)[-1] == "done"
        assert saved_messages(session) == [
            (0, "user", "B"),
            (1, "assistant", "後発"),
            (2, "user", "A"),
            (3, "assistant", "先発"),
        ]

    def test_commits_of_same_plan_append_in_order(self, session):
        """同じ状態から作った計画を続けてコミットしても末尾に追加される."""
        plan = _prepare_plan(session)

        first = commit_turn(plan, "一")
        second = commit_turn(plan, "二")

        assert [first[0].sequence, first[1].sequence] == [0, 1]
        assert [second[0].sequence, second[1].sequence] == [2, 3]


@pytest.mark.django_db
class TestCommitTurn:
    """commit_turn のテスト."""

    def test_commit_without_reply_saves_user_only(self, session):
        plan = _prepare_plan(session)

        user_message, assistant_message = commit_turn(plan, None)

        assert assistant_message is None
        assert user_message.role == "user"
        assert saved_messages(session) == [(0, "user", "今の発話")]

    def test_commit_empty_reply_saves_empty_assistant(self, session):
        plan = _prepare_plan(session)

        _, assistant_message = commit_turn(plan, "")

        assert assistant_message.content == ""
        assert saved_messages(session) == [
            (0, "user", "今の発話"),
            (1, "assistant", ""),
        ]

    def test_commit_missing_session_raises_does_not_exist(self, session):
        plan = _prepare_plan(session)
        ChatSession.objects.filter(id=plan.session.id).delete()

        with pytest.raises(ChatSession.DoesNotExist):
            commit_turn(plan, "x")

    def test_commit_is_atomic(self, session, conversation):
        """途中で失敗すると履歴の削除ごと巻き戻る."""
        plan = _prepare_plan(session, conversation[0])

        with (
            patch(
                "features.talk.chat_turn.create_assistant_message",
                side_effect=RuntimeError("db down"),
            ),
            pytest.raises(RuntimeError),
        ):
            commit_turn(plan, "再生成")

        assert saved_messages(session) == [
            (0, "user", "#0"),
            (1, "assistant", "#1"),
            (2, "user", "#2"),
            (3, "assistant", "#3"),
        ]
