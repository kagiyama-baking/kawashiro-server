"""ChatMessage 削除時の音声ファイル物理削除テスト."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from features.talk.models import ChatMessage, ChatSession

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="signal-test@example.com",
        password="dummypass1234",
        name="Signal User",
    )


def _make_message_with_audio(session: ChatSession, sequence: int = 1) -> ChatMessage:
    audio = ContentFile(b"\x00" * 50, name="audio.wav")
    return ChatMessage.objects.create(
        session=session,
        sequence=sequence,
        role="assistant",
        content="hi",
        audio_file=audio,
        audio_format="wav",
        audio_size_bytes=50,
    )


@pytest.mark.django_db
class TestAudioFileCleanup:
    def test_message_delete_removes_audio_file(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        msg = _make_message_with_audio(session)
        storage = msg.audio_file.storage
        path = msg.audio_file.name
        assert storage.exists(path)

        msg.delete()

        assert not storage.exists(path)

    def test_session_delete_cascades_audio_files(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        m1 = _make_message_with_audio(session, sequence=1)
        m2 = _make_message_with_audio(session, sequence=2)
        storage = m1.audio_file.storage
        p1, p2 = m1.audio_file.name, m2.audio_file.name
        assert storage.exists(p1) and storage.exists(p2)

        session.delete()

        assert not storage.exists(p1)
        assert not storage.exists(p2)

    def test_message_without_audio_delete_does_not_error(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        msg = ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="hi"
        )
        msg.delete()  # 例外なし
        assert ChatMessage.objects.count() == 0
