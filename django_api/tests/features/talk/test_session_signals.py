"""ChatMessage 削除時の音声ファイル物理削除テスト."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction

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
    def test_message_delete_removes_audio_file(
        self, user, django_capture_on_commit_callbacks
    ):
        session = ChatSession.objects.create(user=user, config_name="m")
        msg = _make_message_with_audio(session)
        storage = msg.audio_file.storage
        path = msg.audio_file.name
        assert storage.exists(path)

        with django_capture_on_commit_callbacks(execute=True):
            msg.delete()

        assert not storage.exists(path)

    def test_session_delete_cascades_audio_files(
        self, user, django_capture_on_commit_callbacks
    ):
        session = ChatSession.objects.create(user=user, config_name="m")
        m1 = _make_message_with_audio(session, sequence=1)
        m2 = _make_message_with_audio(session, sequence=2)
        storage = m1.audio_file.storage
        p1, p2 = m1.audio_file.name, m2.audio_file.name
        assert storage.exists(p1) and storage.exists(p2)

        with django_capture_on_commit_callbacks(execute=True):
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

    def test_rolled_back_delete_keeps_audio_file(
        self, user, django_capture_on_commit_callbacks
    ):
        """ロールバックで行が戻るなら、音声ファイルも残す."""
        session = ChatSession.objects.create(user=user, config_name="m")
        msg = _make_message_with_audio(session)
        storage = msg.audio_file.storage
        path = msg.audio_file.name

        with (
            django_capture_on_commit_callbacks(execute=True),
            pytest.raises(RuntimeError),
            transaction.atomic(),
        ):
            msg.delete()
            raise RuntimeError("後続の失敗")

        assert ChatMessage.objects.filter(session=session).count() == 1
        assert storage.exists(path)

    def test_file_is_not_removed_before_commit(
        self, user, django_capture_on_commit_callbacks
    ):
        """コミットの前はファイルに触らない."""
        session = ChatSession.objects.create(user=user, config_name="m")
        msg = _make_message_with_audio(session)
        storage = msg.audio_file.storage
        path = msg.audio_file.name

        with django_capture_on_commit_callbacks(execute=True):
            msg.delete()
            assert storage.exists(path)

        assert not storage.exists(path)

    def test_storage_failure_on_delete_does_not_raise(
        self, user, django_capture_on_commit_callbacks
    ):
        """ファイルの削除に失敗しても、確定済みの削除を失敗にしない."""
        session = ChatSession.objects.create(user=user, config_name="m")
        msg = _make_message_with_audio(session)

        with (
            patch.object(
                msg.audio_file.storage, "delete", side_effect=OSError("disk error")
            ) as storage_delete,
            django_capture_on_commit_callbacks(execute=True),
        ):
            msg.delete()

        storage_delete.assert_called_once()
        assert ChatMessage.objects.filter(session=session).count() == 0
