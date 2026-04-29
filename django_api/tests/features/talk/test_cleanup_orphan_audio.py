"""cleanup_orphan_audio 管理コマンドのテスト."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command

from features.talk.models import ChatMessage, ChatSession

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="cleanup-audio@example.com",
        password="dummypass1234",
    )


def _make_message_with_audio(user, sequence: int = 1) -> ChatMessage:
    session = ChatSession.objects.create(user=user, config_name="m")
    msg = ChatMessage(
        session=session,
        sequence=sequence,
        role="assistant",
        content="hello",
        audio_format="wav",
        audio_size_bytes=20,
    )
    msg.audio_file.save(f"{sequence}.wav", ContentFile(b"\x01" * 20), save=True)
    return msg


@pytest.mark.django_db
class TestCleanupOrphanAudio:
    def test_keeps_records_with_existing_files(self, user):
        msg = _make_message_with_audio(user)
        call_command("cleanup_orphan_audio")
        msg.refresh_from_db()
        assert bool(msg.audio_file)
        assert msg.audio_format == "wav"
        assert msg.audio_size_bytes == 20

    def test_clears_orphan_records(self, user):
        msg = _make_message_with_audio(user)
        # 実体ファイルだけ削除し DB 行は残す（本番事故と同条件）
        msg.audio_file.storage.delete(msg.audio_file.name)

        call_command("cleanup_orphan_audio")

        msg.refresh_from_db()
        assert not msg.audio_file
        assert msg.audio_format == ""
        assert msg.audio_size_bytes == 0

    def test_dry_run_does_not_modify_db(self, user):
        msg = _make_message_with_audio(user)
        msg.audio_file.storage.delete(msg.audio_file.name)
        original_name = msg.audio_file.name
        original_format = msg.audio_format
        original_size = msg.audio_size_bytes

        call_command("cleanup_orphan_audio", "--dry-run")

        msg.refresh_from_db()
        assert msg.audio_file.name == original_name
        assert msg.audio_format == original_format
        assert msg.audio_size_bytes == original_size

    def test_skips_records_without_audio(self, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="hi"
        )

        call_command("cleanup_orphan_audio")

        # 例外なく完了し、対象外レコードに副作用がないこと
        assert ChatMessage.objects.count() == 1
