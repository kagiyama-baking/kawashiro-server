"""LLMClient のテスト."""

from dataclasses import dataclass
from unittest.mock import MagicMock, Mock, patch

import pytest
from openai import APIConnectionError, APITimeoutError

from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMTimeoutError,
)


@dataclass
class MockLLMSettings:
    """テスト用のLLM設定."""

    proxy_base_url: str = "http://litellm-proxy:4000/v1"
    proxy_api_key: str = "sk-test-master-key"
    model_alias: str = "gpt-4o-mini"
    timeout: int = 60
    service_name: str = "talk"
    environment: str = "dev"


@pytest.fixture
def mock_llm_settings():
    """LLM設定のモックフィクスチャ."""
    return MockLLMSettings()


class TestLLMClientInitialization:
    """LLMClient の初期化テスト."""

    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_init_with_service_name(
        self, mock_openai_class, mock_get_settings, mock_llm_settings
    ):
        """サービス名でクライアントを初期化できる."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = mock_llm_settings

        client = LLMClient(service_name="talk")

        assert client.model == "gpt-4o-mini"
        mock_get_settings.assert_called_once_with("talk")
        mock_openai_class.assert_called_once_with(
            base_url="http://litellm-proxy:4000/v1",
            api_key="sk-test-master-key",
            timeout=60,
        )

    @patch("integrations.llm.client.get_llm_settings")
    def test_init_without_config_raises_error(self, mock_get_settings):
        """設定がない場合はエラー."""
        from integrations.llm.client import LLMClient

        mock_get_settings.side_effect = LLMConfigurationError(
            "サービス 'unknown' のLLM設定がありません。"
        )

        with pytest.raises(LLMConfigurationError):
            LLMClient(service_name="unknown")


class TestLLMClientGenerateText:
    """LLMClient のテキスト生成テスト."""

    @pytest.fixture
    def mock_chat_response(self):
        """Chat Completions APIのモックレスポンス."""
        mock_message = Mock()
        mock_message.content = "こんにちは！今日も良い一日を！"
        mock_message.tool_calls = None

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        return mock_response

    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_generate_text_success(
        self,
        mock_openai_class,
        mock_get_settings,
        mock_llm_settings,
        mock_chat_response,
    ):
        """テキスト生成が正常に動作する."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = mock_llm_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chat_response
        mock_openai_class.return_value = mock_client

        client = LLMClient(service_name="talk")
        result = client.generate_text("挨拶して")

        assert result == "こんにちは！今日も良い一日を！"

    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_generate_text_with_system_prompt(
        self,
        mock_openai_class,
        mock_get_settings,
        mock_llm_settings,
        mock_chat_response,
    ):
        """システムプロンプト付きテキスト生成."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = mock_llm_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chat_response
        mock_openai_class.return_value = mock_client

        client = LLMClient(service_name="talk")
        client.generate_text("挨拶して", system_prompt="親しみやすく")

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_generate_text_timeout_raises_llm_timeout(
        self, mock_openai_class, mock_get_settings, mock_llm_settings
    ):
        """タイムアウトでLLMTimeoutErrorを発生."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = mock_llm_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APITimeoutError(
            request=Mock()
        )
        mock_openai_class.return_value = mock_client

        client = LLMClient(service_name="talk")
        with pytest.raises(LLMTimeoutError):
            client.generate_text("挨拶して")

    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_generate_text_connection_error_raises_llm_client_error(
        self, mock_openai_class, mock_get_settings, mock_llm_settings
    ):
        """接続エラーでLLMClientErrorを発生."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = mock_llm_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=Mock()
        )
        mock_openai_class.return_value = mock_client

        client = LLMClient(service_name="talk")
        with pytest.raises(LLMClientError):
            client.generate_text("挨拶して")


class TestLLMClientChatCompletion:
    """LLMClient の Chat Completions テスト（ツール呼び出し対応）."""

    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_chat_completion_with_tools(self, mock_openai_class, mock_get_settings):
        """ツール付きChat Completions呼び出しが動作する."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = MockLLMSettings(service_name="orchestrator")
        mock_response = Mock()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = LLMClient(service_name="orchestrator")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "テストツール",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = client.chat_completion(
            messages=[{"role": "user", "content": "テスト"}],
            tools=tools,
            tool_choice="auto",
        )

        assert result == mock_response
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == "auto"
        assert call_kwargs["extra_body"] == {
            "metadata": {"service_name": "orchestrator", "environment": "dev"}
        }
        assert call_kwargs["name"] == "llm/orchestrator"

    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_chat_completion_without_tools(
        self, mock_openai_class, mock_get_settings, mock_llm_settings
    ):
        """ツールなしChat Completions呼び出しが動作する."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = mock_llm_settings
        mock_response = Mock()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = LLMClient(service_name="talk")
        result = client.chat_completion(
            messages=[{"role": "user", "content": "こんにちは"}],
        )

        assert result == mock_response
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "tools" not in call_kwargs
        assert call_kwargs["extra_body"] == {
            "metadata": {"service_name": "talk", "environment": "dev"}
        }
        assert call_kwargs["name"] == "llm/talk"


class TestLLMClientGenerateEmbedding:
    """LLMClient の Embedding 生成テスト."""

    @patch("integrations.llm.client.httpx")
    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_generate_embedding_success(
        self, mock_openai_class, mock_get_settings, mock_httpx
    ):
        """Embedding生成が正常に動作する."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = MockLLMSettings(service_name="embedding")
        mock_openai_class.return_value = MagicMock()
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        mock_response.raise_for_status = Mock()
        mock_httpx.post.return_value = mock_response

        client = LLMClient(service_name="embedding")
        result = client.generate_embedding("テストテキスト")

        assert result == [0.1, 0.2, 0.3]
        call_kwargs = mock_httpx.post.call_args
        body = call_kwargs.kwargs["json"]
        assert body["model"] == "gpt-4o-mini"
        assert body["input"] == "テストテキスト"
        assert "vector_store_ids" not in body

    @patch("integrations.llm.client.httpx")
    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_generate_embedding_with_dimensions(
        self, mock_openai_class, mock_get_settings, mock_httpx, mock_llm_settings
    ):
        """次元数指定付きEmbedding生成."""
        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = mock_llm_settings
        mock_openai_class.return_value = MagicMock()
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"embedding": [0.1, 0.2]}]}
        mock_response.raise_for_status = Mock()
        mock_httpx.post.return_value = mock_response

        client = LLMClient(service_name="embedding")
        client.generate_embedding("テスト", dimensions=512)

        body = mock_httpx.post.call_args.kwargs["json"]
        assert body["dimensions"] == 512

    @patch("integrations.llm.client.httpx")
    @patch("integrations.llm.client.get_llm_settings")
    @patch("integrations.llm.client.OpenAI")
    def test_generate_embedding_timeout(
        self, mock_openai_class, mock_get_settings, mock_httpx, mock_llm_settings
    ):
        """Embeddingタイムアウトでエラー."""
        import httpx as real_httpx

        from integrations.llm.client import LLMClient

        mock_get_settings.return_value = mock_llm_settings
        mock_openai_class.return_value = MagicMock()
        mock_httpx.post.side_effect = real_httpx.TimeoutException("timeout")
        mock_httpx.TimeoutException = real_httpx.TimeoutException
        mock_httpx.HTTPError = real_httpx.HTTPError

        client = LLMClient(service_name="embedding")
        with pytest.raises(LLMTimeoutError):
            client.generate_embedding("テスト")
