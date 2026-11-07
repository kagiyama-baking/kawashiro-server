"""TalkService のチャット応答（prepare_chat_prompt / stream_chat_reply）のテスト."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from features.talk.services import TalkService
from integrations.langfuse.exceptions import LangfusePromptError, PromptUnavailableError
from integrations.llm.exceptions import LLMClientError, LLMConfigurationError
from tests.fixtures.factories import (
    AgentSkillFactory,
    PromptFactory,
    TalkSettingFactory,
)
from tests.fixtures.llm import LiteLLMStreamBody, litellm_stream, stream_of
from tests.fixtures.sse import SEPARATE_DELTAS

SYSTEM_PROMPT = "あなたは親切なアシスタントです。"
# シーン（スキル）の本文を置く Langfuse のプロンプト名（スキル名そのもの）
SCENE_NAME = "talk-scene-cafe"
SCENE_BODY = "カフェで向かい合って、ゆっくり話している。"


@pytest.fixture(autouse=True)
def _langfuse_prompts(langfuse_prompts):
    """Langfuse は代役にする（入れた本文だけを返す）."""
    return langfuse_prompts


@pytest.fixture
def chat_setting(db, langfuse_prompts):
    """システムプロンプトだけの Talk 設定（本文は Langfuse の production にある）."""
    langfuse_prompts[("talk-chat-system", "production")] = SYSTEM_PROMPT
    ref = PromptFactory(name="talk-chat-system")
    return TalkSettingFactory(name="チャットテスト設定", system_prompt=ref)


@pytest.fixture
def scene(langfuse_prompts):
    """本文を Langfuse（staging）に置いたシーン."""
    langfuse_prompts[(SCENE_NAME, "staging")] = f"\n  {SCENE_BODY}\n"
    return AgentSkillFactory(name=SCENE_NAME, label="staging")


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
    """TalkService.prepare_chat_prompt（Talk 設定のシステムプロンプト + シーン）のテスト."""

    def test_prepare_chat_prompt_without_scene_returns_system_prompt(
        self, talk_llm_settings, chat_setting
    ):
        """シーンがなければ、システムプロンプトの本文だけを返す."""
        assert TalkService().prepare_chat_prompt(chat_setting) == SYSTEM_PROMPT

    def test_prepare_chat_prompt_with_scene_appends_scene_section(
        self, talk_llm_settings, chat_setting, scene
    ):
        """シーンがあれば、本文を「# シーン設定」の節としてシステムプロンプトの後ろに足す."""
        prompt = TalkService().prepare_chat_prompt(chat_setting, scene)

        assert prompt == f"{SYSTEM_PROMPT}\n\n# シーン設定\n\n{SCENE_BODY}"

    def test_prepare_chat_prompt_does_not_expand_variables(
        self, talk_llm_settings, langfuse_prompts
    ):
        """システムプロンプトとシーンの変数は展開しない（外部のデータを取りに行かない）."""
        langfuse_prompts[("talk-vars-system", "production")] = "現在時刻: {{datetime}}"
        ref = PromptFactory(name="talk-vars-system")
        langfuse_prompts[(SCENE_NAME, "staging")] = "天気: {{weather}}"

        prompt = TalkService().prepare_chat_prompt(
            TalkSettingFactory(system_prompt=ref),
            AgentSkillFactory(name=SCENE_NAME, label="staging"),
        )

        assert "{{datetime}}" in prompt
        assert "{{weather}}" in prompt

    def test_prepare_chat_prompt_without_system_prompt_in_langfuse_raises_error(
        self, talk_llm_settings, chat_setting, langfuse_prompts
    ):
        """システムプロンプトを Langfuse から取れなければ PromptUnavailableError（フォールバックはない）."""
        del langfuse_prompts[("talk-chat-system", "production")]

        with pytest.raises(PromptUnavailableError) as exc_info:
            TalkService().prepare_chat_prompt(chat_setting)

        assert exc_info.value.prompt_name == "talk-chat-system"
        assert isinstance(exc_info.value.__cause__, LangfusePromptError)

    def test_prepare_chat_prompt_with_empty_system_prompt_raises_error(
        self, talk_llm_settings, langfuse_prompts
    ):
        """システムプロンプトの本文が空なら PromptUnavailableError（空のまま話さない）."""
        langfuse_prompts[("talk-empty-system", "production")] = " \n"
        ref = PromptFactory(name="talk-empty-system")

        with pytest.raises(PromptUnavailableError) as exc_info:
            TalkService().prepare_chat_prompt(TalkSettingFactory(system_prompt=ref))

        assert exc_info.value.prompt_name == "talk-empty-system"

    def test_prepare_chat_prompt_without_llm_config_raises_before_langfuse(
        self, chat_setting, langfuse_unreachable
    ):
        """LLM 設定がなければ、Langfuse に問い合わせる前に LLMConfigurationError になる."""
        with pytest.raises(LLMConfigurationError):
            TalkService().prepare_chat_prompt(
                chat_setting, AgentSkillFactory(name=SCENE_NAME)
            )


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
        chat_llm.enqueue(stream_of("一", "二", gap=SEPARATE_DELTAS))

        assert _reply() == ["一", "二"]

    def test_stream_chat_reply_does_not_expand_user_messages(self, chat_llm):
        """user メッセージ内の {{datetime}} は展開しない（純粋な対話）."""
        chat_llm.enqueue("OK")

        _reply([{"role": "user", "content": "今日は {{datetime}} です"}])

        assert chat_llm.requests[0].user_prompt == "今日は {{datetime}} です"

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

    def test_langfuse_session_release_failure_does_not_break_chat(self, chat_llm):
        chat_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            mock_propagate.return_value.__exit__.side_effect = RuntimeError("boom")
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
