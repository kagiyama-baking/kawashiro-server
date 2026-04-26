"""TalkService.generate_session_title のテスト."""

from unittest.mock import MagicMock, patch

import pytest

from features.talk.services import TalkService


def _mock_completion(content: str):
    response = MagicMock()
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


class TestGenerateSessionTitle:
    def test_empty_messages_returns_empty_string(self):
        service = TalkService()
        assert service.generate_session_title([]) == ""

    @patch("features.talk.services.LLMClient")
    def test_returns_trimmed_title(self, mock_llm_class):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_completion(
            "「日常会話のあいさつ」 \n余分な行"
        )
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        title = service.generate_session_title(
            [
                {"role": "user", "content": "おはよう"},
                {"role": "assistant", "content": "おはようございます"},
            ]
        )
        # 引用符と末尾改行が除去され、1行目のみ
        assert title == "日常会話のあいさつ"

    @patch("features.talk.services.LLMClient")
    def test_truncates_long_title(self, mock_llm_class):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_completion("あ" * 80)
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        title = service.generate_session_title([{"role": "user", "content": "x"}])
        assert len(title) == TalkService.SESSION_TITLE_MAX_LENGTH

    @patch("features.talk.services.LLMClient")
    def test_llm_failure_returns_empty(self, mock_llm_class):
        mock_llm = MagicMock()
        mock_llm.chat_completion.side_effect = RuntimeError("LLM down")
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        title = service.generate_session_title([{"role": "user", "content": "x"}])
        assert title == ""

    @patch("features.talk.services.LLMClient")
    def test_session_id_propagates_to_langfuse(self, mock_llm_class):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_completion("OK")
        mock_llm_class.return_value = mock_llm

        with patch("langfuse.get_client") as mock_get_client:
            service = TalkService()
            service.generate_session_title(
                [{"role": "user", "content": "x"}],
                session_id="sess-abc",
            )
            mock_get_client.return_value.update_current_trace.assert_called_with(
                session_id="sess-abc"
            )

    @patch("features.talk.services.LLMClient")
    def test_no_session_id_does_not_set_session(self, mock_llm_class):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_completion("OK")
        mock_llm_class.return_value = mock_llm

        with patch("langfuse.get_client") as mock_get_client:
            service = TalkService()
            service.generate_session_title([{"role": "user", "content": "x"}])
            mock_get_client.return_value.update_current_trace.assert_not_called()
