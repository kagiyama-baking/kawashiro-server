"""talk ビュー共通ヘルパ（例外の分類・音声の保存）のテスト."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db.models.query import QuerySet

from features.talk.models import ChatMessage, ChatSession
from features.talk.views._common import (
    attach_audio_to_message,
    classify_synthesis_error,
    get_owned_session,
)
from integrations.langfuse.exceptions import PromptUnavailableError
from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMOutputError,
    LLMTimeoutError,
)
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError

User = get_user_model()

FALLBACK = "フォールバック"

# チャットのターンで起きる例外（LLM・TTS・プロンプトの準備）
CLASSIFICATION = [
    (LLMTimeoutError("x"), 504, "サービスへのリクエストがタイムアウトしました"),
    (TTSTimeoutError("x"), 504, "サービスへのリクエストがタイムアウトしました"),
    (LLMClientError("x"), 502, "AI生成サービスへの接続に失敗しました"),
    (LLMOutputError("x"), 502, "AI生成サービスへの接続に失敗しました"),
    (TTSNetworkError("x"), 502, "AI生成サービスへの接続に失敗しました"),
    # LLM の設定がない・プロンプトの本文を使えないのは、設定の問題として 503
    (LLMConfigurationError("x"), 503, "サービスの設定に問題があります"),
    (PromptUnavailableError("x"), 503, "サービスの設定に問題があります"),
    (RuntimeError("内部の詳細"), 500, FALLBACK),
]


@pytest.mark.unit
class TestClassifySynthesisError:
    """例外の分類（HTTP と SSE の error・audio_error で共用）."""

    @pytest.mark.parametrize(("exc", "status_code", "error"), CLASSIFICATION)
    def test_classify_synthesis_error_returns_status_and_message(
        self, exc, status_code, error
    ):
        assert classify_synthesis_error(exc, FALLBACK) == (status_code, error)

    def test_unknown_error_is_logged_with_traceback_outside_except_block(self, caplog):
        """except の外から呼ばれても、想定外の例外のトレースバックをログに残す."""
        try:
            raise RuntimeError("内部の詳細")
        except RuntimeError as caught:
            exc = caught

        classify_synthesis_error(exc, FALLBACK)

        record = next(r for r in caplog.records if r.levelname == "ERROR")
        assert record.exc_info is not None
        assert record.exc_info[1] is exc


@pytest.fixture
def media_root(settings, tmp_path):
    """音声の保存先をテストごとの一時ディレクトリにする."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def assistant_message(db, media_root):
    user = User.objects.create_user(email="common@example.com", password="x12345678")
    session = ChatSession.objects.create(user=user)
    return ChatMessage.objects.create(
        session=session, sequence=1, role="assistant", content="本文"
    )


def _audio_files(media_root) -> list:
    return [path for path in media_root.rglob("*") if path.is_file()]


@pytest.mark.django_db
class TestAttachAudioToMessage:
    """attach_audio_to_message のテスト."""

    def test_attach_audio_saves_file_and_fields(self, assistant_message, media_root):
        """ファイルと音声フィールドを保存して True を返す."""
        assert attach_audio_to_message(assistant_message, b"\x00" * 8, "wav") is True

        saved = ChatMessage.objects.get(id=assistant_message.id)
        assert saved.audio_file.read() == b"\x00" * 8
        assert saved.audio_format == "wav"
        assert saved.audio_size_bytes == 8
        # 渡したインスタンスも同じ状態になる（シリアライズに使う）
        assert assistant_message.audio_file.name == saved.audio_file.name
        assert assistant_message.audio_format == "wav"
        assert assistant_message.audio_size_bytes == 8

    def test_attach_audio_to_deleted_message_leaves_no_file(
        self, assistant_message, media_root
    ):
        """行が削除済みならファイルを残さず False を返す."""
        ChatMessage.objects.filter(id=assistant_message.id).delete()

        assert attach_audio_to_message(assistant_message, b"\x00" * 8, "wav") is False
        assert _audio_files(media_root) == []

    def test_attach_audio_storage_failure_returns_false(self, assistant_message):
        """ストレージの失敗では例外を出さず False を返し、本文は残す."""
        with patch.object(
            assistant_message.audio_file.storage,
            "save",
            side_effect=OSError("disk full"),
        ):
            assert (
                attach_audio_to_message(assistant_message, b"\x00" * 8, "wav") is False
            )

        saved = ChatMessage.objects.get(id=assistant_message.id)
        assert saved.content == "本文"
        assert not saved.audio_file
        assert saved.audio_size_bytes == 0

    def test_attach_audio_db_failure_leaves_no_file(
        self, assistant_message, media_root
    ):
        """DB の更新に失敗したらファイルを残さず False を返す."""
        with patch.object(QuerySet, "update", side_effect=RuntimeError("db down")):
            assert (
                attach_audio_to_message(assistant_message, b"\x00" * 8, "wav") is False
            )

        assert _audio_files(media_root) == []

    def test_attach_audio_cleanup_failure_returns_false(self, assistant_message):
        """後始末の失敗でも例外を出さず False を返す."""
        storage = assistant_message.audio_file.storage

        with (
            patch.object(QuerySet, "update", side_effect=RuntimeError("db down")),
            patch.object(storage, "delete", side_effect=OSError("disk error")),
        ):
            assert (
                attach_audio_to_message(assistant_message, b"\x00" * 8, "wav") is False
            )


@pytest.mark.django_db
def test_get_owned_session_loads_setting_scene_and_system_prompt_in_one_query(
    django_assert_num_queries,
):
    """ターンの事前検証で使う Talk 設定・シーン・システムプロンプトの参照を一度に引く."""
    from tests.fixtures.factories import AgentSkillFactory, TalkSettingFactory

    owner = get_user_model().objects.create_user(
        email="owned-session@example.com", password="dummypass1234"
    )
    scene = AgentSkillFactory(name="talk-scene-cafe")
    setting = TalkSettingFactory(skills=[scene])
    created = ChatSession.objects.create(user=owner, setting=setting, skill=scene)

    with django_assert_num_queries(1):
        session = get_owned_session(SimpleNamespace(user=owner), created.pk)
        loaded = (session.setting.system_prompt.name, session.skill.name)

    assert loaded == (setting.system_prompt.name, "talk-scene-cafe")
