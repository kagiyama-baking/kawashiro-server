"""TalkService.synthesize_chat (sessions API の内部呼び出し) のテスト."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart

from features.talk.exceptions import PlaceholderDataMissingError
from features.talk.llm_agents import TALK_CHAT_AGENT
from features.talk.models import TalkConfig
from features.talk.services import TalkService
from integrations.langfuse.models import LangfusePromptRef
from integrations.llm.exceptions import LLMConfigurationError
from integrations.tts.client import TTSResult
from tests.fixtures.llm import ScriptedLLM


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    """Langfuse 接続を切って fallback_text 経由に統一する."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.fixture
def chat_llm(talk_llm_settings):
    """チャットエージェントの応答を台本で固定する."""
    llm = ScriptedLLM()
    with TALK_CHAT_AGENT.override(model=llm.model):
        yield llm


@pytest.fixture
def chat_prompt_refs(db):
    sys_ref = LangfusePromptRef.objects.create(
        name="talk-chat-system",
        langfuse_prompt_name="talk-chat-system",
        fallback_text="あなたは親切なアシスタントです。",
    )
    user_ref = LangfusePromptRef.objects.create(
        name="talk-chat-user",
        langfuse_prompt_name="talk-chat-user",
        fallback_text="dummy user prompt",
    )
    return sys_ref, user_ref


@pytest.fixture
def chat_config(chat_prompt_refs):
    return TalkConfig.objects.create(
        name="chat_test",
        display_name="チャットテスト設定",
        tts_enabled=False,
        system_prompt_ref=chat_prompt_refs[0],
        user_prompt_ref=chat_prompt_refs[1],
    )


@pytest.fixture
def chat_config_with_tts(chat_prompt_refs):
    return TalkConfig.objects.create(
        name="chat_tts_test",
        display_name="チャットTTSテスト設定",
        tts_enabled=True,
        tts_model="test_model",
        tts_style="Happy",
        system_prompt_ref=chat_prompt_refs[0],
        user_prompt_ref=chat_prompt_refs[1],
    )


@pytest.mark.django_db
class TestTalkServiceChat:
    """TalkService.synthesize_chat のテスト"""

    def test_synthesize_chat_single_turn(self, chat_llm, chat_config):
        chat_llm.enqueue("こんにちは、先輩")

        service = TalkService()
        result = service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "こんにちは"}],
        )

        assert result["message"]["role"] == "assistant"
        assert result["message"]["content"] == "こんにちは、先輩"
        assert "audio_data" not in result

        request = chat_llm.requests[0]
        assert request.instructions == "あなたは親切なアシスタントです。"
        assert request.conversation == [("user", "こんにちは")]

    def test_synthesize_chat_multi_turn_passes_full_history(
        self, chat_llm, chat_config
    ):
        chat_llm.enqueue("最近どうですか")

        messages = [
            {"role": "user", "content": "こんにちは"},
            {"role": "assistant", "content": "こんにちは"},
            {"role": "user", "content": "今日の調子はどう？"},
        ]
        service = TalkService()
        result = service.synthesize_chat(config=chat_config, messages=messages)

        assert result["message"]["content"] == "最近どうですか"

        request = chat_llm.requests[0]
        assert request.instructions == "あなたは親切なアシスタントです。"
        assert request.conversation == [
            ("user", "こんにちは"),
            ("assistant", "こんにちは"),
            ("user", "今日の調子はどう？"),
        ]

    @patch("features.talk.services.TTSClient")
    def test_synthesize_chat_with_tts(
        self, mock_tts_class, chat_llm, chat_config_with_tts
    ):
        chat_llm.enqueue("お返事です")

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = TTSResult(
            audio_data=b"fake_wav", content_type="audio/wav", format="wav"
        )
        mock_tts_class.return_value = mock_tts

        service = TalkService()
        result = service.synthesize_chat(
            config=chat_config_with_tts,
            messages=[{"role": "user", "content": "テスト"}],
        )

        assert result["audio_data"] == b"fake_wav"
        assert result["audio_format"] == "wav"
        mock_tts.synthesize.assert_called_once()
        assert mock_tts.synthesize.call_args.kwargs["text"] == "お返事です"

    @patch("features.talk.services.HolidayClient")
    def test_synthesize_chat_expands_system_placeholder(
        self, mock_holiday_class, chat_llm, db
    ):
        sys_ref = LangfusePromptRef.objects.create(
            name="chat-sys-dt",
            langfuse_prompt_name="chat-sys-dt",
            fallback_text="現在時刻: {{datetime}}",
        )
        user_ref = LangfusePromptRef.objects.create(
            name="chat-usr-dt",
            langfuse_prompt_name="chat-usr-dt",
            fallback_text="dummy",
        )
        config = TalkConfig.objects.create(
            name="chat_with_dt",
            display_name="日時付きチャット",
            system_prompt_ref=sys_ref,
            user_prompt_ref=user_ref,
        )

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        chat_llm.enqueue("OK")

        service = TalkService()
        service.synthesize_chat(
            config=config,
            messages=[{"role": "user", "content": "今何時？"}],
        )

        sent_system = chat_llm.requests[0].instructions
        assert "{{datetime}}" not in sent_system
        assert "day_of_week" in sent_system

    def test_synthesize_chat_weather_requires_area_code(self, db):
        sys_ref = LangfusePromptRef.objects.create(
            name="chat-sys-w",
            langfuse_prompt_name="chat-sys-w",
            fallback_text="天気: {{weather}}",
        )
        user_ref = LangfusePromptRef.objects.create(
            name="chat-usr-w",
            langfuse_prompt_name="chat-usr-w",
            fallback_text="dummy",
        )
        config = TalkConfig.objects.create(
            name="chat_no_area",
            display_name="天気付きだが area_code なし",
            area_code="",
            system_prompt_ref=sys_ref,
            user_prompt_ref=user_ref,
        )

        service = TalkService()
        with pytest.raises(PlaceholderDataMissingError):
            service.synthesize_chat(
                config=config,
                messages=[{"role": "user", "content": "テスト"}],
            )

    @patch("features.talk.services.HolidayClient")
    def test_synthesize_chat_does_not_expand_user_messages(
        self, mock_holiday_class, chat_llm, chat_config
    ):
        """user メッセージ内の {{datetime}} は展開しない（純粋な対話）."""
        chat_llm.enqueue("OK")

        service = TalkService()
        service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "今日は {{datetime}} です"}],
        )

        assert chat_llm.requests[0].user_prompt == "今日は {{datetime}} です"
        mock_holiday_class.return_value.get_holiday_name.assert_not_called()

    def test_synthesize_chat_empty_reply_returns_empty_text_without_retry(
        self, chat_llm, chat_config
    ):
        """本文のない応答は再試行せず空文字にする（従来の `content or ""` と同じ）."""
        chat_llm.enqueue(ModelResponse(parts=[TextPart(content="")]))

        service = TalkService()
        result = service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result["message"]["content"] == ""
        assert len(chat_llm.requests) == 1

    @pytest.mark.parametrize("finish_reason", ["length", "content_filter"])
    def test_synthesize_chat_reply_emptied_by_provider_returns_empty_text(
        self, finish_reason, chat_llm, chat_config
    ):
        """出力上限やフィルターで本文がなくても例外にせず空文字にする（従来と同じ）."""
        chat_llm.enqueue(ModelResponse(parts=[], finish_reason=finish_reason))

        service = TalkService()
        result = service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result["message"]["content"] == ""
        assert len(chat_llm.requests) == 1

    def test_synthesize_chat_sends_service_metadata(self, chat_llm, chat_config):
        """LiteLLM 向けの metadata を送る."""
        chat_llm.enqueue("OK")

        service = TalkService()
        service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "hi"}],
        )

        assert chat_llm.requests[0].model_settings["extra_body"] == {
            "metadata": {"service_name": "talk", "environment": "test"}
        }

    def test_synthesize_chat_without_llm_config_raises_configuration_error(
        self, chat_config
    ):
        """LLM 設定がなければ従来どおり LLMConfigurationError になる."""
        service = TalkService()
        with pytest.raises(LLMConfigurationError):
            service.synthesize_chat(
                config=chat_config,
                messages=[{"role": "user", "content": "hi"}],
            )


@pytest.mark.django_db
class TestTalkServiceChatLangfuseSession:
    """synthesize_chat に session_id を渡すと Langfuse トレースに反映される."""

    def test_session_id_propagates_to_langfuse(self, chat_llm, chat_config):
        chat_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            service = TalkService()
            service.synthesize_chat(
                config=chat_config,
                messages=[{"role": "user", "content": "hi"}],
                session_id="abc-123",
            )
            mock_propagate.assert_called_once_with(session_id="abc-123")
            mock_propagate.return_value.__enter__.assert_called_once()
            mock_propagate.return_value.__exit__.assert_called_once()

    def test_no_session_id_does_not_set_session(self, chat_llm, chat_config):
        chat_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            service = TalkService()
            service.synthesize_chat(
                config=chat_config,
                messages=[{"role": "user", "content": "hi"}],
            )
            # session_id が無いときは属性の伝播を始めない
            mock_propagate.assert_not_called()

    def test_langfuse_session_failure_does_not_break_chat(self, chat_llm, chat_config):
        chat_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            mock_propagate.return_value.__enter__.side_effect = RuntimeError("boom")
            service = TalkService()
            result = service.synthesize_chat(
                config=chat_config,
                messages=[{"role": "user", "content": "hi"}],
                session_id="abc-123",
            )
        assert result["message"]["content"] == "OK"


@pytest.mark.django_db
class TestTalkServiceChatMaxTokens:
    """LLM 呼び出し時に max_tokens 上限が指定されることのテスト"""

    def test_synthesize_chat_passes_max_tokens(self, chat_llm, chat_config):
        chat_llm.enqueue("OK")

        service = TalkService()
        service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "test"}],
        )

        settings = chat_llm.requests[0].model_settings
        assert settings["max_tokens"] == TalkService.CHAT_MAX_OUTPUT_TOKENS
        assert TalkService.CHAT_MAX_OUTPUT_TOKENS == 1024
