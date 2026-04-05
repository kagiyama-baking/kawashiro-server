"""Langfuseプロンプト取得ヘルパーのテスト."""

from unittest.mock import MagicMock, patch

import pytest

from features.hn_agent.prompts import get_prompt

FALLBACK = "これはフォールバックプロンプトです。"


@pytest.mark.unit
class TestGetPrompt:
    """get_prompt関数のテスト."""

    @patch("langfuse.get_client")
    def test_returns_langfuse_prompt_when_available(self, mock_get_client):
        """Langfuseからプロンプトを正常取得できる."""
        mock_client = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "Langfuseのプロンプト"
        mock_client.get_prompt.return_value = mock_prompt
        mock_get_client.return_value = mock_client

        result = get_prompt("test-prompt", FALLBACK)

        assert result == "Langfuseのプロンプト"
        mock_client.get_prompt.assert_called_once_with("test-prompt")

    @patch("langfuse.get_client")
    def test_returns_fallback_when_langfuse_errors(self, mock_get_client):
        """Langfuseエラー時にフォールバック値を返す."""
        mock_get_client.side_effect = RuntimeError("connection failed")

        result = get_prompt("test-prompt", FALLBACK)

        assert result == FALLBACK

    @patch("langfuse.get_client")
    def test_returns_fallback_when_prompt_not_found(self, mock_get_client):
        """プロンプト未登録時にフォールバック値を返す."""
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = Exception("Prompt not found")
        mock_get_client.return_value = mock_client

        result = get_prompt("test-prompt", FALLBACK)

        assert result == FALLBACK

    @patch("langfuse.get_client", side_effect=ImportError("No module"))
    def test_returns_fallback_when_import_error(self, _mock):
        """ImportError時にフォールバック値を返す."""
        result = get_prompt("test-prompt", FALLBACK)

        assert result == FALLBACK
