"""ChatSession / ChatMessage モデルのテスト."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import IntegrityError

from features.talk.models import ChatMessage, ChatSession

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="chat-history@example.com",
        password="dummypass1234",
        name="History User",
    )


@pytest.mark.django_db
class TestChatSession:
    def test_create_with_required_fields(self, user):
        session = ChatSession.objects.create(user=user, config_name="morning")
        assert isinstance(session.id, uuid.UUID)
        assert session.user_id == user.id
        assert session.config_name == "morning"
        assert session.title == ""
        assert session.created_at is not None
        assert session.updated_at is not None

    def test_default_ordering_is_recent_first(self, user):
        s1 = ChatSession.objects.create(user=user, config_name="a")
        s2 = ChatSession.objects.create(user=user, config_name="b")
        ids = list(ChatSession.objects.values_list("id", flat=True))
        assert ids == [s2.id, s1.id]

    def test_str_uses_title_or_fallback(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        assert "ChatSession" in str(session) or session.config_name in str(session)
        session.title = "テストタイトル"
        session.save()
        assert "テストタイトル" in str(session)

    def test_user_cascade_deletes_sessions(self, user):
        ChatSession.objects.create(user=user, config_name="m")
        ChatSession.objects.create(user=user, config_name="e")
        user.delete()
        assert ChatSession.objects.count() == 0


@pytest.mark.django_db
class TestChatMessage:
    def test_create_user_message(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        msg = ChatMessage.objects.create(
            session=session,
            sequence=0,
            role="user",
            content="おはよう",
        )
        assert msg.role == "user"
        assert msg.content == "おはよう"
        assert msg.sequence == 0
        assert msg.audio_size_bytes == 0
        assert not msg.audio_file

    def test_create_assistant_with_audio(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        audio = ContentFile(b"\x00" * 100, name="reply.wav")
        msg = ChatMessage.objects.create(
            session=session,
            sequence=1,
            role="assistant",
            content="おはようございます",
            audio_file=audio,
            audio_format="wav",
            audio_size_bytes=100,
        )
        assert msg.audio_file
        assert msg.audio_size_bytes == 100
        assert msg.audio_format == "wav"

    def test_unique_session_sequence(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="a"
        )
        with pytest.raises(IntegrityError):
            ChatMessage.objects.create(
                session=session, sequence=0, role="assistant", content="b"
            )

    def test_default_ordering_is_sequence(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        ChatMessage.objects.create(
            session=session, sequence=2, role="user", content="3"
        )
        ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="1"
        )
        ChatMessage.objects.create(
            session=session, sequence=1, role="assistant", content="2"
        )
        contents = list(session.messages.values_list("content", flat=True))
        assert contents == ["1", "2", "3"]

    def test_session_cascade_deletes_messages(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="hi"
        )
        ChatMessage.objects.create(
            session=session, sequence=1, role="assistant", content="hello"
        )
        session.delete()
        assert ChatMessage.objects.count() == 0
