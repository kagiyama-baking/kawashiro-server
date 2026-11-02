"""talk ビュー共通ヘルパ（例外の分類・音声の保存）のテスト."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db.models.query import QuerySet

from features.talk.exceptions import (
    HolidayNetworkError,
    HolidayTimeoutError,
    PlaceholderDataMissingError,
)
from features.talk.models import ChatMessage, ChatSession
from features.talk.views._common import (
    attach_audio_to_message,
    classify_synthesis_error,
    handle_synthesis_error,
)
from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMOutputError,
    LLMTimeoutError,
)
from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError
from integrations.weather.exceptions import (
    WeatherAreaNotFoundError,
    WeatherNetworkError,
    WeatherParseError,
    WeatherTimeoutError,
)

User = get_user_model()

FALLBACK = "フォールバック"

CLASSIFICATION = [
    (PlaceholderDataMissingError("設定不足"), 400, "設定不足"),
    (WeatherAreaNotFoundError("x"), 404, "指定された予報区コードが見つかりません"),
    (
        WeatherTimeoutError("x"),
        504,
        "外部サービスへのリクエストがタイムアウトしました",
    ),
    (LLMTimeoutError("x"), 504, "サービスへのリクエストがタイムアウトしました"),
    (TTSTimeoutError("x"), 504, "サービスへのリクエストがタイムアウトしました"),
    (HolidayTimeoutError("x"), 504, "サービスへのリクエストがタイムアウトしました"),
    (WeatherNetworkError("x"), 502, "外部サービスへの接続に失敗しました"),
    (WeatherParseError("x"), 502, "外部サービスへの接続に失敗しました"),
    (NetworkError("x"), 502, "外部サービスへの接続に失敗しました"),
    (HolidayNetworkError("x"), 502, "外部サービスへの接続に失敗しました"),
    (LLMClientError("x"), 502, "AI生成サービスへの接続に失敗しました"),
    (LLMOutputError("x"), 502, "AI生成サービスへの接続に失敗しました"),
    (TTSNetworkError("x"), 502, "AI生成サービスへの接続に失敗しました"),
    (ConfigurationError("x"), 503, "サービスの設定に問題があります"),
    (AuthenticationError("x"), 502, "外部サービスへの認証に失敗しました"),
    (LLMConfigurationError("x"), 500, FALLBACK),
    (RuntimeError("内部の詳細"), 500, FALLBACK),
]


@pytest.mark.unit
class TestClassifySynthesisError:
    """例外の分類（HTTP と SSE の error で共用）."""

    @pytest.mark.parametrize(("exc", "status_code", "error"), CLASSIFICATION)
    def test_classify_synthesis_error_returns_status_and_message(
        self, exc, status_code, error
    ):
        assert classify_synthesis_error(exc, FALLBACK) == (status_code, error)

    @pytest.mark.parametrize(("exc", "status_code", "error"), CLASSIFICATION)
    def test_handle_synthesis_error_uses_same_classification(
        self, exc, status_code, error
    ):
        response = handle_synthesis_error(exc, fallback_message=FALLBACK)

        assert response.status_code == status_code
        assert response.data == {"error": error}

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
    session = ChatSession.objects.create(user=user, config_name="c")
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
