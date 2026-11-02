"""TalkService.generate_session_title のテスト."""

from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart

from features.talk.llm_agents import TALK_TITLE_AGENT
from features.talk.services import TalkService
from integrations.llm.exceptions import LLMConfigurationError
from tests.fixtures.llm import ScriptedLLM


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.fixture
def title_llm(talk_llm_settings):
    """タイトル生成エージェントの応答を台本で固定する."""
    llm = ScriptedLLM()
    with TALK_TITLE_AGENT.override(model=llm.model):
        yield llm


class TestGenerateSessionTitle:
    def test_empty_messages_returns_empty_string(self):
        service = TalkService()
        assert service.generate_session_title([]) == ""

    def test_returns_trimmed_title(self, title_llm):
        title_llm.enqueue("「日常会話のあいさつ」 \n余分な行")

        service = TalkService()
        title = service.generate_session_title(
            [
                {"role": "user", "content": "おはよう"},
                {"role": "assistant", "content": "おはようございます"},
            ]
        )
        # 引用符と末尾改行が除去され、1行目のみ
        assert title == "日常会話のあいさつ"

    def test_truncates_long_title(self, title_llm):
        title_llm.enqueue("あ" * 80)

        service = TalkService()
        title = service.generate_session_title([{"role": "user", "content": "x"}])
        assert len(title) == TalkService.SESSION_TITLE_MAX_LENGTH

    def test_llm_failure_returns_empty(self, title_llm):
        title_llm.enqueue(RuntimeError("LLM down"))

        service = TalkService()
        title = service.generate_session_title([{"role": "user", "content": "x"}])
        assert title == ""

    def test_missing_llm_config_returns_empty(self, talk_llm_settings):
        """LLM 設定がなくても例外にせず空文字を返す."""
        talk_llm_settings.side_effect = LLMConfigurationError("no config")

        service = TalkService()
        title = service.generate_session_title([{"role": "user", "content": "x"}])
        assert title == ""

    def test_empty_reply_returns_empty_without_retry(self, title_llm):
        """本文のない応答は再試行せず空文字にする."""
        title_llm.enqueue(ModelResponse(parts=[TextPart(content="")]))

        service = TalkService()
        title = service.generate_session_title([{"role": "user", "content": "x"}])

        assert title == ""
        assert len(title_llm.requests) == 1

    def test_request_uses_token_limit_and_first_four_messages(self, title_llm):
        """出力上限を指定し、入力は先頭 4 件だけを 1 つのプロンプトにまとめる."""
        title_llm.enqueue("タイトル")
        messages = [{"role": "user", "content": f"発言{i}"} for i in range(6)]

        service = TalkService()
        service.generate_session_title(messages)

        request = title_llm.requests[0]
        settings = request.model_settings
        assert settings["max_tokens"] == TalkService.SESSION_TITLE_MAX_OUTPUT_TOKENS
        assert TalkService.SESSION_TITLE_MAX_OUTPUT_TOKENS == 60
        assert "タイトル" in request.instructions
        assert request.conversation == [
            ("user", "user: 発言0\nuser: 発言1\nuser: 発言2\nuser: 発言3")
        ]

    def test_session_id_propagates_to_langfuse(self, title_llm):
        title_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            service = TalkService()
            service.generate_session_title(
                [{"role": "user", "content": "x"}],
                session_id="sess-abc",
            )
            mock_propagate.assert_called_once_with(session_id="sess-abc")
            mock_propagate.return_value.__enter__.assert_called_once()
            mock_propagate.return_value.__exit__.assert_called_once()

    def test_no_session_id_does_not_set_session(self, title_llm):
        title_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            service = TalkService()
            service.generate_session_title([{"role": "user", "content": "x"}])
            mock_propagate.assert_not_called()

    def test_langfuse_session_failure_does_not_break_title(self, title_llm):
        title_llm.enqueue("OK")

        with patch("langfuse.propagate_attributes") as mock_propagate:
            mock_propagate.return_value.__enter__.side_effect = RuntimeError("boom")
            service = TalkService()
            title = service.generate_session_title(
                [{"role": "user", "content": "x"}],
                session_id="sess-abc",
            )
        assert title == "OK"
