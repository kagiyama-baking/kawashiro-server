"""PATCH /talk/sessions/<id>/messages/<msg_id>/ (編集再送) のテスト（JSON モード）.

`Accept` に `text/event-stream` を含まないときの応答を確かめる。SSE モードは
`test_chat_turn_sse.py`、LLM はモデルだけを差し替えて実行する。
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from pydantic_ai.exceptions import ModelHTTPError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.models import ChatMessage, ChatSession, TalkSetting
from integrations.langfuse.models import LangfusePromptRef

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="edit-view@example.com",
        password="dummypass1234",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="edit-other@example.com",
        password="dummypass1234",
    )


def _client_for(u):
    token, _ = Token.objects.get_or_create(user=u)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return c


@pytest.fixture
def auth_client(user):
    return _client_for(user)


@pytest.fixture
def system_prompt(db, langfuse_prompts):
    """Talk 設定のシステムプロンプトの参照（本文は Langfuse の代役の production にある）."""
    langfuse_prompts[("edit-system", "production")] = "system"
    return LangfusePromptRef.objects.create(
        name="edit-system", langfuse_prompt_name="edit-system"
    )


@pytest.fixture
def talk_setting(system_prompt):
    return TalkSetting.objects.create(
        name="編集再送用", system_prompt_ref=system_prompt
    )


@pytest.fixture
def populated_session(user, talk_setting):
    """user/assistant が複数件入った session を作る."""
    session = ChatSession.objects.create(
        user=user, setting=talk_setting, title="既存タイトル"
    )
    msgs = []
    for i in range(4):
        # 0:user 1:assistant 2:user 3:assistant
        m = ChatMessage(
            session=session,
            sequence=i,
            role="user" if i % 2 == 0 else "assistant",
            content=f"#{i}",
        )
        if i % 2 == 1:
            m.audio_format = "wav"
            m.audio_size_bytes = 30
            m.audio_file.save(f"{i}.wav", ContentFile(b"\x02" * 30), save=False)
        m.save()
        msgs.append(m)
    return session, msgs


def _url(session_id, msg_id) -> str:
    return f"/talk/sessions/{session_id}/messages/{msg_id}/"


@pytest.mark.django_db
class TestSessionMessageEdit:
    def test_unauthenticated_returns_401(self, populated_session):
        session, msgs = populated_session
        response = APIClient().patch(
            _url(session.id, msgs[0].id), {"content": "x"}, format="json"
        )
        assert response.status_code == 401

    def test_other_user_returns_404(self, populated_session, other_user):
        session, msgs = populated_session
        response = _client_for(other_user).patch(
            _url(session.id, msgs[0].id), {"content": "x"}, format="json"
        )
        assert response.status_code == 404

    def test_editing_assistant_message_returns_400(
        self, populated_session, auth_client
    ):
        session, msgs = populated_session
        # msgs[1] は assistant
        response = auth_client.patch(
            _url(session.id, msgs[1].id), {"content": "x"}, format="json"
        )
        assert response.status_code == 400

    def test_empty_content_returns_400(self, populated_session, auth_client):
        session, msgs = populated_session
        response = auth_client.patch(
            _url(session.id, msgs[0].id), {"content": ""}, format="json"
        )
        assert response.status_code == 400

    def test_edit_drops_subsequent_messages_and_audio(
        self,
        chat_llm,
        populated_session,
        auth_client,
        django_capture_on_commit_callbacks,
    ):
        session, msgs = populated_session
        chat_llm.enqueue("再生成された応答")

        # 削除対象の audio file path を覚えておく
        a1_path = msgs[1].audio_file.name
        a3_path = msgs[3].audio_file.name
        storage = msgs[1].audio_file.storage
        assert storage.exists(a1_path) and storage.exists(a3_path)

        # msgs[0] (user, sequence=0) を編集
        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client.patch(
                _url(session.id, msgs[0].id),
                {"content": "編集後"},
                format="json",
            )

        assert response.status_code == 200
        # 残るのは新 user (sequence=0) + 新 assistant (sequence=1)
        remaining = list(session.messages.order_by("sequence"))
        assert len(remaining) == 2
        assert remaining[0].role == "user" and remaining[0].content == "編集後"
        assert remaining[1].role == "assistant"
        assert remaining[1].content == "再生成された応答"
        # 旧音声は物理削除済み
        assert not storage.exists(a1_path) and not storage.exists(a3_path)

    def test_edit_keeps_existing_title(
        self, chat_llm, title_llm, populated_session, auth_client
    ):
        session, msgs = populated_session
        chat_llm.enqueue("再生成")

        auth_client.patch(_url(session.id, msgs[0].id), {"content": "x"}, format="json")

        session.refresh_from_db()
        # タイトルがあれば編集再送でも再生成しない（既存維持）
        assert session.title == "既存タイトル"
        assert title_llm.requests == []

    def test_edit_through_real_agent_sends_prior_history_and_replaces_rest(
        self, chat_llm, populated_session, auth_client
    ):
        """モデル以外を差し替えずに通し、対象より前の履歴だけを LLM に渡す."""
        session, msgs = populated_session
        chat_llm.enqueue("再生成された返信")

        response = auth_client.patch(
            _url(session.id, msgs[2].id), {"content": "編集後"}, format="json"
        )

        assert response.status_code == 200
        assert chat_llm.requests[0].conversation == [
            ("user", "#0"),
            ("assistant", "#1"),
            ("user", "編集後"),
        ]
        assert [m.content for m in session.messages.order_by("sequence")] == [
            "#0",
            "#1",
            "編集後",
            "再生成された返信",
        ]
        assert [m["content"] for m in response.data["messages"]] == [
            "#0",
            "#1",
            "編集後",
            "再生成された返信",
        ]

    @pytest.mark.parametrize("status_code", [429, 500])
    def test_llm_status_error_returns_502_and_keeps_messages_and_audio(
        self, status_code, chat_llm, populated_session, auth_client
    ):
        """LLM の HTTP エラーは 502 になり、既存のメッセージも音声も残る.

        以前は行だけがロールバックされ、音声ファイルは削除されたままになっていた。
        """
        session, msgs = populated_session
        audio_names = [msgs[1].audio_file.name, msgs[3].audio_file.name]
        storage = msgs[1].audio_file.storage
        chat_llm.enqueue(ModelHTTPError(status_code, "test-alias"))

        response = auth_client.patch(
            _url(session.id, msgs[0].id), {"content": "編集後"}, format="json"
        )

        assert response.status_code == 502
        assert [m.content for m in session.messages.order_by("sequence")] == [
            "#0",
            "#1",
            "#2",
            "#3",
        ]
        assert all(storage.exists(name) for name in audio_names)

    def test_message_not_in_session_returns_404(self, populated_session, auth_client):
        session, msgs = populated_session
        # 別 session を作って、その msg id を渡す
        other_session = ChatSession.objects.create(
            user=session.user, setting=session.setting
        )
        other_msg = ChatMessage.objects.create(
            session=other_session, sequence=0, role="user", content="他"
        )
        response = auth_client.patch(
            _url(session.id, other_msg.id), {"content": "x"}, format="json"
        )
        assert response.status_code == 404

    def test_other_user_msg_id_returns_404(
        self, populated_session, auth_client, other_user
    ):
        """他ユーザーの msg_id を URL に混ぜても 404 になる（IDOR 防御）."""
        session, _ = populated_session
        other_session = ChatSession.objects.create(
            user=other_user, setting=session.setting
        )
        other_msg = ChatMessage.objects.create(
            session=other_session, sequence=0, role="user", content="他人の発言"
        )
        # URL の session_id は自分のもの、msg_id は他人のもの
        response = auth_client.patch(
            _url(session.id, other_msg.id), {"content": "x"}, format="json"
        )
        assert response.status_code == 404
        # 他人のメッセージが消されていないこと
        assert ChatMessage.objects.filter(id=other_msg.id).exists()
