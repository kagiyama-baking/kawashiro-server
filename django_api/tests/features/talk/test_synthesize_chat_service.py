"""TalkService.synthesize_chat (sessions API の内部呼び出し) のテスト."""

from unittest.mock import MagicMock, patch

import pytest

from features.talk.exceptions import PlaceholderDataMissingError
from features.talk.models import TalkConfig
from features.talk.services import TalkService
from integrations.langfuse.models import LangfusePromptRef
from integrations.tts.client import TTSResult


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    """Langfuse 接続を切って fallback_text 経由に統一する."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


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


def _mock_chat_completion(content: str):
    response = MagicMock()
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


@pytest.mark.django_db
class TestTalkServiceChat:
    """TalkService.synthesize_chat のテスト"""

    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_single_turn(self, mock_llm_class, chat_config):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion(
            "こんにちは、先輩"
        )
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        result = service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "こんにちは"}],
        )

        assert result["message"]["role"] == "assistant"
        assert result["message"]["content"] == "こんにちは、先輩"
        assert "audio_data" not in result

        sent_messages = mock_llm.chat_completion.call_args.args[0]
        assert sent_messages[0]["role"] == "system"
        assert sent_messages[1]["role"] == "user"
        assert sent_messages[1]["content"] == "こんにちは"

    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_multi_turn_passes_full_history(
        self, mock_llm_class, chat_config
    ):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("最近どうですか")
        mock_llm_class.return_value = mock_llm

        messages = [
            {"role": "user", "content": "こんにちは"},
            {"role": "assistant", "content": "こんにちは"},
            {"role": "user", "content": "今日の調子はどう？"},
        ]
        service = TalkService()
        result = service.synthesize_chat(config=chat_config, messages=messages)

        assert result["message"]["content"] == "最近どうですか"

        sent = mock_llm.chat_completion.call_args.args[0]
        assert sent[0]["role"] == "system"
        assert len(sent) == 4
        assert [m["content"] for m in sent[1:]] == [
            "こんにちは",
            "こんにちは",
            "今日の調子はどう？",
        ]

    @patch("features.talk.services.LLMClient")
    @patch("features.talk.services.TTSClient")
    def test_synthesize_chat_with_tts(
        self, mock_tts_class, mock_llm_class, chat_config_with_tts
    ):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("お返事です")
        mock_llm_class.return_value = mock_llm

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
    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_expands_system_placeholder(
        self, mock_llm_class, mock_holiday_class, db
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

        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("OK")
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        service.synthesize_chat(
            config=config,
            messages=[{"role": "user", "content": "今何時？"}],
        )

        sent_system = mock_llm.chat_completion.call_args.args[0][0]["content"]
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
    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_does_not_expand_user_messages(
        self, mock_llm_class, mock_holiday_class, chat_config
    ):
        """user メッセージ内の {{datetime}} は展開しない（純粋な対話）."""
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("OK")
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "今日は {{datetime}} です"}],
        )

        sent = mock_llm.chat_completion.call_args.args[0]
        assert sent[1]["content"] == "今日は {{datetime}} です"
        mock_holiday_class.return_value.get_holiday_name.assert_not_called()


@pytest.mark.django_db
class TestTalkServiceChatMaxTokens:
    """LLM 呼び出し時に max_tokens 上限が指定されることのテスト"""

    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_passes_max_tokens(self, mock_llm_class, chat_config):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("OK")
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "test"}],
        )

        call_kwargs = mock_llm.chat_completion.call_args.kwargs
        assert call_kwargs.get("max_tokens") == TalkService.CHAT_MAX_OUTPUT_TOKENS
