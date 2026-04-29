"""音声配信・削除エンドポイントのテスト."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.models import ChatMessage, ChatSession

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="audio-view@example.com",
        password="dummypass1234",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="audio-other@example.com",
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
def session_with_audio(user):
    session = ChatSession.objects.create(user=user, config_name="m")
    ChatMessage.objects.create(session=session, sequence=0, role="user", content="hi")
    msg = ChatMessage(
        session=session,
        sequence=1,
        role="assistant",
        content="hello",
        audio_format="wav",
        audio_size_bytes=20,
    )
    msg.audio_file.save("1.wav", ContentFile(b"\x01" * 20), save=True)
    return session, msg


def _audio_url(session_id, msg_id) -> str:
    return f"/talk/sessions/{session_id}/audio/{msg_id}/"


def _bulk_url(session_id) -> str:
    return f"/talk/sessions/{session_id}/audio/"


@pytest.mark.django_db
class TestAudioGet:
    def test_unauthenticated_returns_401(self, session_with_audio):
        session, msg = session_with_audio
        response = APIClient().get(_audio_url(session.id, msg.id))
        assert response.status_code == 401

    def test_other_user_returns_404(self, session_with_audio, other_user):
        session, msg = session_with_audio
        response = _client_for(other_user).get(_audio_url(session.id, msg.id))
        assert response.status_code == 404

    def test_returns_audio_bytes(self, session_with_audio, auth_client):
        session, msg = session_with_audio
        response = auth_client.get(_audio_url(session.id, msg.id))
        assert response.status_code == 200
        assert response["Content-Type"].startswith("audio/")
        # streaming レスポンスの場合 streaming_content を結合
        body = b"".join(response.streaming_content)
        assert len(body) == 20

    def test_message_without_audio_returns_404(self, auth_client, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        msg = ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="hi"
        )
        response = auth_client.get(_audio_url(session.id, msg.id))
        assert response.status_code == 404

    def test_storage_missing_returns_404(self, session_with_audio, auth_client):
        """DB には audio_file パスが残るが実体ファイルが消えていれば 404."""
        session, msg = session_with_audio
        # ボリューム喪失等で実体だけ消えた状況を再現（DB 行はそのまま）
        msg.audio_file.storage.delete(msg.audio_file.name)

        response = auth_client.get(_audio_url(session.id, msg.id))

        assert response.status_code == 404


@pytest.mark.django_db
class TestAudioDeleteIndividual:
    def test_delete_clears_audio_keeps_message(self, session_with_audio, auth_client):
        session, msg = session_with_audio
        path = msg.audio_file.name
        storage = msg.audio_file.storage
        assert storage.exists(path)

        response = auth_client.delete(_audio_url(session.id, msg.id))

        assert response.status_code == 204
        msg.refresh_from_db()
        assert not msg.audio_file
        assert msg.audio_size_bytes == 0
        assert msg.audio_format == ""
        assert ChatMessage.objects.filter(id=msg.id).exists()
        assert not storage.exists(path)

    def test_delete_other_user_returns_404(self, session_with_audio, other_user):
        session, msg = session_with_audio
        response = _client_for(other_user).delete(_audio_url(session.id, msg.id))
        assert response.status_code == 404


@pytest.mark.django_db
class TestAudioBulkDelete:
    def test_bulk_delete_removes_all_audio_keeps_messages(self, auth_client, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="u1"
        )
        for i, content in enumerate(["a1", "a2"], start=1):
            m = ChatMessage(
                session=session,
                sequence=i,
                role="assistant",
                content=content,
                audio_format="wav",
                audio_size_bytes=10,
            )
            m.audio_file.save(f"{i}.wav", ContentFile(b"\x00" * 10), save=True)

        response = auth_client.delete(_bulk_url(session.id))

        assert response.status_code == 204
        # メッセージは残る
        assert session.messages.count() == 3
        # 全 assistant の audio が空
        for m in session.messages.filter(role="assistant"):
            assert not m.audio_file
            assert m.audio_size_bytes == 0

    def test_bulk_delete_other_user_returns_404(self, session_with_audio, other_user):
        session, _ = session_with_audio
        response = _client_for(other_user).delete(_bulk_url(session.id))
        assert response.status_code == 404
