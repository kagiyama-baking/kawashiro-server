"""TalkService のチャット応答（prepare_chat_prompt / stream_chat_reply）のテスト."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from features.talk.exceptions import PlaceholderDataMissingError
from features.talk.models import TalkConfig
from features.talk.services import TalkService
from integrations.langfuse.models import LangfusePromptRef
from integrations.llm.exceptions import LLMClientError, LLMConfigurationError
from tests.fixtures.llm import LiteLLMStreamBody, litellm_stream, stream_of

SYSTEM_PROMPT = "あなたは親切なアシスタントです。"


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
        fallback_text=SYSTEM_PROMPT,
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


def _config_with_system_prompt(name: str, system_text: str, **fields) -> TalkConfig:
    sys_ref = LangfusePromptRef.objects.create(
        name=f"{name}-sys",
        langfuse_prompt_name=f"{name}-sys",
        fallback_text=system_text,
    )
    user_ref = LangfusePromptRef.objects.create(
        name=f"{name}-usr", langfuse_prompt_name=f"{name}-usr", fallback_text="dummy"
    )
    return TalkConfig.objects.create(
        name=name,
        display_name=name,
        system_prompt_ref=sys_ref,
        user_prompt_ref=user_ref,
        **fields,
    )


def _reply(messages: list[dict[str, str]] | None = None, **kwargs) -> list[str]:
    """応答のストリームを最後まで読み、増分の並びを返す."""
    return list(
        TalkService().stream_chat_reply(
            SYSTEM_PROMPT,
            messages or [{"role": "user", "content": "hi"}],
            **kwargs,
        )
    )


@pytest.mark.django_db
class TestPrepareChatPrompt:
    """TalkService.prepare_chat_prompt のテスト."""

    def test_prepare_chat_prompt_returns_system_prompt(
        self, talk_llm_settings, chat_config
    ):
        """system プロンプトの本文を返す."""
        assert TalkService().prepare_chat_prompt(chat_config) == SYSTEM_PROMPT

    @patch("features.talk.services.HolidayClient")
    def test_prepare_chat_prompt_expands_placeholder(
        self, mock_holiday_class, talk_llm_settings
    ):
        """system プロンプトのプレースホルダーは取得したデータで展開する."""
        mock_holiday_class.return_value.get_holiday_name.return_value = None
        config = _config_with_system_prompt("chat_with_dt", "現在時刻: {{datetime}}")

        system_prompt = TalkService().prepare_chat_prompt(config)

        assert "{{datetime}}" not in system_prompt
        assert "day_of_week" in system_prompt

    def test_prepare_chat_prompt_weather_requires_area_code(self, talk_llm_settings):
        """{{weather}} があるのに予報区コードがなければ外部 API を呼ぶ前に失敗する."""
        config = _config_with_system_prompt(
            "chat_no_area", "天気: {{weather}}", area_code=""
        )

        with pytest.raises(PlaceholderDataMissingError):
            TalkService().prepare_chat_prompt(config)

    def test_prepare_chat_prompt_without_llm_config_raises_configuration_error(
        self, chat_config
    ):
        """LLM 設定がなければストリームを始める前に LLMConfigurationError になる."""
        with pytest.raises(LLMConfigurationError):
            TalkService().prepare_chat_prompt(chat_config)


@pytest.mark.django_db
class TestStreamChatReply:
    """TalkService.stream_chat_reply のテスト."""

    def test_stream_chat_reply_single_turn(self, chat_llm):
        """本文の増分を返し、system プロンプトと発話を LLM に渡す."""
        chat_llm.enqueue("こんにちは、先輩")

        assert _reply([{"role": "user", "content": "こんにちは"}]) == [
            "こんにちは、先輩"
        ]

        request = chat_llm.requests[0]
        assert request.instructions == SYSTEM_PROMPT
        assert request.conversation == [("user", "こんにちは")]

    def test_stream_chat_reply_multi_turn_passes_full_history(self, chat_llm):
        """過去の履歴を順に渡す."""
        chat_llm.enqueue("最近どうですか")

        _reply(
            [
                {"role": "user", "content": "こんにちは"},
                {"role": "assistant", "content": "こんにちは"},
                {"role": "user", "content": "今日の調子はどう？"},
            ]
        )

        request = chat_llm.requests[0]
        assert request.instructions == SYSTEM_PROMPT
        assert request.conversation == [
            ("user", "こんにちは"),
            ("assistant", "こんにちは"),
            ("user", "今日の調子はどう？"),
        ]

    def test_stream_chat_reply_chunks_arrive_in_order(self, chat_llm):
        """増分は届いた順に返り、連結すると本文になる."""
        chat_llm.enqueue(stream_of("一", "二", gap=0.12))

        assert _reply() == ["一", "二"]

    @patch("features.talk.services.HolidayClient")
    def test_stream_chat_reply_does_not_expand_user_messages(
        self, mock_holiday_class, chat_llm
    ):
        """user メッセージ内の {{datetime}} は展開しない（純粋な対話）."""
        chat_llm.enqueue("OK")

        _reply([{"role": "user", "content": "今日は {{datetime}} です"}])

        assert chat_llm.requests[0].user_prompt == "今日は {{datetime}} です"
        mock_holiday_class.return_value.get_holiday_name.assert_not_called()

    def test_stream_chat_reply_blank_text_yields_nothing_without_retry(self, chat_llm):
        """空の本文は増分なしで終わり、再試行しない."""
        chat_llm.enqueue("")

        assert _reply() == []
        assert len(chat_llm.requests) == 1

    def test_stream_chat_reply_thinking_only_yields_nothing_without_retry(
        self, chat_llm
    ):
        """思考だけで本文のない応答は増分なしで終わり、再試行しない."""
        chat_llm.enqueue(stream_of())

        assert _reply() == []
        assert len(chat_llm.requests) == 1

    @pytest.mark.parametrize("finish_reason", ["stop", "length", "content_filter"])
    def test_stream_chat_reply_emptied_by_provider_yields_nothing(
        self, finish_reason, fake_litellm, talk_llm_settings
    ):
        """出力上限やフィルターで本文がなくても例外にしない（LiteLLM の応答の解釈まで通す）."""
        fake = fake_litellm(
            litellm_stream({"role": "assistant"}, finish_reason=finish_reason)
        )

        assert _reply() == []
        assert len(fake.requests) == 1

    def test_stream_chat_reply_sends_service_metadata(self, chat_llm):
        """LiteLLM 向けの metadata を送る."""
        chat_llm.enqueue("OK")

        _reply()

        assert chat_llm.requests[0].model_settings["extra_body"] == {
            "metadata": {"service_name": "talk", "environment": "test"}
        }

    def test_stream_chat_reply_passes_max_tokens(self, chat_llm):
        """LLM 呼び出し時に max_tokens の上限を指定する."""
        chat_llm.enqueue("OK")

        _reply()

        settings = chat_llm.requests[0].model_settings
        assert settings["max_tokens"] == TalkService.CHAT_MAX_OUTPUT_TOKENS
        assert TalkService.CHAT_MAX_OUTPUT_TOKENS == 1024

    def test_stream_chat_reply_body_contract(self, fake_litellm, talk_llm_settings):
        """LiteLLM へ送る本文の契約（system と max_tokens）."""
        fake = fake_litellm(litellm_stream("OK"))

        _reply()

        body = fake.bodies[0]
        assert body["stream"] is True
        assert body["max_tokens"] == 1024
        assert body["messages"] == [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "hi"},
        ]

    def test_stream_chat_reply_llm_error_is_translated(self, chat_llm):
        """LLM のエラーはプロジェクトの例外になる."""
        chat_llm.enqueue(ModelHTTPError(500, "test-alias"))

        with pytest.raises(LLMClientError):
            _reply()

    def test_stream_chat_reply_without_llm_config_raises_configuration_error(self):
        """LLM 設定がなければ LLMConfigurationError になる."""
        with pytest.raises(LLMConfigurationError):
            _reply()

    def test_stream_chat_reply_close_midway_closes_llm_stream(
        self, fake_litellm, talk_llm_settings
    ):
        """途中で閉じると LiteLLM への接続もその場で閉じる."""
        body = LiteLLMStreamBody("途中", hang=True)
        fake = fake_litellm(body.response())
        stream = TalkService().stream_chat_reply(
            SYSTEM_PROMPT, [{"role": "user", "content": "hi"}]
        )

        assert next(stream) == "途中"
        stream.close()

        assert body.closed
        assert fake.clients[0].is_closed()


@pytest.mark.django_db
class TestStreamChatReplyLangfuseSession:
    """session_id を渡すと Langfuse トレースに反映される."""

    def test_session_id_propagates_to_langfuse(self, chat_llm):
        chat_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            _reply(session_id="abc-123")

        mock_propagate.assert_called_once_with(session_id="abc-123")
        mock_propagate.return_value.__enter__.assert_called_once()
        mock_propagate.return_value.__exit__.assert_called_once()

    def test_session_is_released_when_closed_midway(self, chat_llm):
        """途中で閉じても属性の伝播を解除する."""
        chat_llm.enqueue(stream_of("途中", hang=True))

        with patch("langfuse.propagate_attributes") as mock_propagate:
            stream = TalkService().stream_chat_reply(
                SYSTEM_PROMPT,
                [{"role": "user", "content": "hi"}],
                session_id="abc-123",
            )
            next(stream)
            mock_propagate.return_value.__exit__.assert_not_called()
            stream.close()

        mock_propagate.return_value.__exit__.assert_called_once()

    def test_no_session_id_does_not_set_session(self, chat_llm):
        chat_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            _reply()

        # session_id が無いときは属性の伝播を始めない
        mock_propagate.assert_not_called()

    def test_langfuse_session_failure_does_not_break_chat(self, chat_llm):
        chat_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            mock_propagate.return_value.__enter__.side_effect = RuntimeError("boom")
            deltas = _reply(session_id="abc-123")

        assert deltas == ["OK"]


@pytest.mark.django_db
class TestSynthesizeAudio:
    """TalkService.synthesize_audio のテスト."""

    @patch("features.talk.services.TTSClient")
    def test_synthesize_audio_passes_text_and_options(self, mock_tts_class):
        """本文と TTS 設定を TTS クライアントへ渡す."""
        mock_tts = MagicMock()
        mock_tts_class.return_value = mock_tts
        options = {
            "model": "test_model",
            "style": "Happy",
            "style_weight": 1.0,
            "speed": 1.0,
            "sdp_ratio": 0.2,
            "noise_scale": 0.6,
            "noise_scale_w": 0.8,
            "format": "wav",
        }

        TalkService().synthesize_audio("お返事です", options)

        mock_tts.synthesize.assert_called_once()
        kwargs = mock_tts.synthesize.call_args.kwargs
        assert kwargs["text"] == "お返事です"
        assert kwargs["model"] == "test_model"
        assert kwargs["style"] == "Happy"
