"""PATCH /talk/sessions/<id>/messages/<msg_id>/ (編集再送) のテスト."""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.models import ChatMessage, ChatSession, TalkConfig
from integrations.langfuse.models import LangfusePromptRef

User = get_user_model()


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


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
def prompt_refs(db):
    sys_ref = LangfusePromptRef.objects.create(
        name="edit-system",
        langfuse_prompt_name="edit-system",
        fallback_text="system",
    )
    user_ref = LangfusePromptRef.objects.create(
        name="edit-user",
        langfuse_prompt_name="edit-user",
        fallback_text="user",
    )
    return sys_ref, user_ref


@pytest.fixture
def talk_config(prompt_refs):
    sys_ref, user_ref = prompt_refs
    return TalkConfig.objects.create(
        name="edit-config",
        display_name="編集再送用",
        tts_enabled=False,
        system_prompt_ref=sys_ref,
        user_prompt_ref=user_ref,
    )


@pytest.fixture
def populated_session(user, talk_config):
    """user/assistant が複数件入った session を作る."""
    session = ChatSession.objects.create(
        user=user, config_name=talk_config.name, title="既存タイトル"
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


def _mock_service(content="再生成"):
    svc = MagicMock()
    svc.synthesize_chat.return_value = {
        "message": {"role": "assistant", "content": content}
    }
    svc.generate_session_title.return_value = "新タイトル"
    return svc


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

    @patch("features.talk.views.TalkService")
    def test_edit_drops_subsequent_messages_and_audio(
        self, mock_service_class, populated_session, auth_client
    ):
        session, msgs = populated_session
        mock_service_class.return_value = _mock_service("再生成された応答")

        # 削除対象の audio file path を覚えておく
        a1_path = msgs[1].audio_file.name
        a3_path = msgs[3].audio_file.name
        storage = msgs[1].audio_file.storage
        assert storage.exists(a1_path) and storage.exists(a3_path)

        # msgs[0] (user, sequence=0) を編集
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

    @patch("features.talk.views.TalkService")
    def test_edit_keeps_existing_title(
        self, mock_service_class, populated_session, auth_client
    ):
        session, msgs = populated_session
        mock_service_class.return_value = _mock_service()

        auth_client.patch(_url(session.id, msgs[0].id), {"content": "x"}, format="json")

        session.refresh_from_db()
        # 編集再送ではタイトル再生成しない（既存維持）
        assert session.title == "既存タイトル"

    @patch("features.talk.views.TalkService")
    def test_synthesis_error_rollbacks(
        self, mock_service_class, populated_session, auth_client
    ):
        from integrations.llm.exceptions import LLMClientError

        session, msgs = populated_session
        original_count = session.messages.count()
        original_seq0_content = msgs[0].content

        svc = MagicMock()
        svc.synthesize_chat.side_effect = LLMClientError("nope")
        mock_service_class.return_value = svc

        response = auth_client.patch(
            _url(session.id, msgs[0].id),
            {"content": "編集予定だった"},
            format="json",
        )

        assert response.status_code == 502
        # ロールバック: メッセージ件数も内容も保持される
        assert session.messages.count() == original_count
        msgs[0].refresh_from_db()
        assert msgs[0].content == original_seq0_content

    def test_message_not_in_session_returns_404(self, populated_session, auth_client):
        session, msgs = populated_session
        # 別 session を作って、その msg id を渡す
        other_session = ChatSession.objects.create(
            user=session.user, config_name=session.config_name
        )
        other_msg = ChatMessage.objects.create(
            session=other_session, sequence=0, role="user", content="他"
        )
        response = auth_client.patch(
            _url(session.id, other_msg.id), {"content": "x"}, format="json"
        )
        assert response.status_code == 404
