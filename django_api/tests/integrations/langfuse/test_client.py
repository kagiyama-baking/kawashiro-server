"""resolve_prompt のテスト."""

from unittest.mock import MagicMock, patch

import pytest

from integrations.langfuse.client import resolve_prompt
from integrations.langfuse.models import LangfusePromptRef


@pytest.fixture
def ref(db):
    """テスト用プロンプト参照."""
    return LangfusePromptRef.objects.create(
        name="test-ref",
        langfuse_prompt_name="test-prompt",
        label="production",
        fallback_text="fallback: {{name}} ({{count}})",
    )


@pytest.mark.integration
class TestResolvePrompt:
    """resolve_prompt のテスト."""

    @patch("langfuse.get_client")
    def test_returns_langfuse_prompt_when_available(self, mock_get_client, ref):
        """Langfuse から取得成功したら compile 済みテキストを返す."""
        mock_client = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "compiled text"
        mock_client.get_prompt.return_value = mock_prompt
        mock_get_client.return_value = mock_client

        result = resolve_prompt(ref, name="alice", count=3)

        assert result == "compiled text"
        mock_client.get_prompt.assert_called_once_with(
            "test-prompt", label="production"
        )
        mock_prompt.compile.assert_called_once_with(name="alice", count=3)

    @patch("langfuse.get_client")
    def test_returns_fallback_when_langfuse_errors(self, mock_get_client, ref):
        """Langfuse エラー時は fallback を変数置換して返す."""
        mock_get_client.side_effect = RuntimeError("connection failed")

        result = resolve_prompt(ref, name="alice", count=3)

        assert result == "fallback: alice (3)"

    @patch("langfuse.get_client")
    def test_returns_fallback_when_prompt_not_found(self, mock_get_client, ref):
        """プロンプト未登録時も fallback を返す."""
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = Exception("Prompt not found")
        mock_get_client.return_value = mock_client

        result = resolve_prompt(ref, name="bob", count=0)

        assert result == "fallback: bob (0)"

    @patch("langfuse.get_client", side_effect=ImportError("No module"))
    def test_returns_fallback_when_import_error(self, _mock, ref):
        """langfuse 未インストール時も fallback を返す."""
        result = resolve_prompt(ref, name="bob", count=0)

        assert result == "fallback: bob (0)"

    @patch("langfuse.get_client")
    def test_fallback_keeps_unknown_placeholders(self, mock_get_client, db):
        """未知のプレースホルダーは元の `{{key}}` のまま残す."""
        mock_get_client.side_effect = RuntimeError("boom")
        ref = LangfusePromptRef.objects.create(
            name="partial",
            langfuse_prompt_name="partial",
            fallback_text="hello {{name}} / {{unknown}}",
        )

        result = resolve_prompt(ref, name="world")

        assert result == "hello world / {{unknown}}"

    @patch("langfuse.get_client")
    def test_fallback_without_variables(self, mock_get_client, db):
        """variables が無くても fallback は機能する."""
        mock_get_client.side_effect = RuntimeError("boom")
        ref = LangfusePromptRef.objects.create(
            name="plain",
            langfuse_prompt_name="plain",
            fallback_text="static text",
        )

        result = resolve_prompt(ref)

        assert result == "static text"

    @patch("langfuse.get_client")
    def test_resolves_label(self, mock_get_client, db):
        """staging ラベルも指定される."""
        mock_client = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "ok"
        mock_client.get_prompt.return_value = mock_prompt
        mock_get_client.return_value = mock_client

        ref = LangfusePromptRef.objects.create(
            name="staging-ref",
            langfuse_prompt_name="hello",
            label="staging",
        )

        resolve_prompt(ref, who="there")

        mock_client.get_prompt.assert_called_once_with("hello", label="staging")
