"""Tests for OpenAI API client."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from openai import APIConnectionError, APITimeoutError

from integrations.llm.config import OpenAISettings
from integrations.llm.exceptions import (
    OpenAIAPIError,
    OpenAIConfigurationError,
    OpenAITimeoutError,
)
from integrations.llm.openai_client import OpenAIClient


@pytest.fixture
def mock_openai_settings():
    """OpenAI設定のモックフィクスチャ."""
    return OpenAISettings(
        api_key="test-db-api-key",
        model="gpt-4o-mini",
        embedding_model="text-embedding-3-small",
        timeout=60,
    )


class TestOpenAIClientInitialization:
    """OpenAIClientの初期化テスト."""

    @patch("integrations.llm.openai_client.get_openai_settings")
    def test_init_uses_db_settings(self, mock_get_settings, mock_openai_settings):
        """DB設定を使用して初期化できる."""
        mock_get_settings.return_value = mock_openai_settings

        client = OpenAIClient()

        assert client.api_key == "test-db-api-key"
        assert client.model == "gpt-4o-mini"
        assert client.timeout == 60

    @patch("integrations.llm.openai_client.get_openai_settings")
    def test_init_with_explicit_api_key(self, mock_get_settings, mock_openai_settings):
        """明示的なAPIキーがDB設定より優先される."""
        mock_get_settings.return_value = mock_openai_settings

        client = OpenAIClient(api_key="explicit-api-key")

        assert client.api_key == "explicit-api-key"
        assert client.model == "gpt-4o-mini"  # DB設定を使用

    @patch("integrations.llm.openai_client.get_openai_settings")
    def test_init_with_custom_model(self, mock_get_settings, mock_openai_settings):
        """カスタムモデルを指定して初期化できる."""
        mock_get_settings.return_value = mock_openai_settings

        client = OpenAIClient(model="gpt-4o")

        assert client.model == "gpt-4o"

    @patch("integrations.llm.openai_client.get_openai_settings")
    def test_init_without_db_settings_raises_error(self, mock_get_settings):
        """DB設定がない場合はエラー."""
        mock_get_settings.side_effect = OpenAIConfigurationError(
            "有効なOpenAI API設定がありません。"
        )

        with pytest.raises(OpenAIConfigurationError) as exc_info:
            OpenAIClient()
        assert "設定" in str(exc_info.value)


class TestOpenAIClientGenerateText:
    """OpenAIClientのテキスト生成テスト."""

    @pytest.fixture
    def mock_openai_response(self):
        """OpenAI APIのモックレスポンス."""
        mock_message = Mock()
        mock_message.content = "こんにちは！今日も良い一日を！"

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        return mock_response

    @patch("integrations.llm.openai_client.get_openai_settings")
    @patch("integrations.llm.openai_client.OpenAI")
    def test_generate_text_success(
        self,
        mock_openai_class,
        mock_get_settings,
        mock_openai_settings,
        mock_openai_response,
    ):
        """テキスト生成が正常に動作する."""
        mock_get_settings.return_value = mock_openai_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient()
        result = client.generate_text("挨拶して")

        assert result == "こんにちは！今日も良い一日を！"
        mock_client.chat.completions.create.assert_called_once()

    @patch("integrations.llm.openai_client.get_openai_settings")
    @patch("integrations.llm.openai_client.OpenAI")
    def test_generate_text_with_system_prompt(
        self,
        mock_openai_class,
        mock_get_settings,
        mock_openai_settings,
        mock_openai_response,
    ):
        """システムプロンプトを指定してテキスト生成ができる."""
        mock_get_settings.return_value = mock_openai_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient()
        client.generate_text("挨拶して", system_prompt="親しみやすく話してください")

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "親しみやすく話してください"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "挨拶して"

    @patch("integrations.llm.openai_client.get_openai_settings")
    @patch("integrations.llm.openai_client.OpenAI")
    def test_generate_text_timeout_error(
        self, mock_openai_class, mock_get_settings, mock_openai_settings
    ):
        """タイムアウト時にOpenAITimeoutErrorを発生させる."""
        mock_get_settings.return_value = mock_openai_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APITimeoutError(
            request=Mock()
        )
        mock_openai_class.return_value = mock_client

        client = OpenAIClient()

        with pytest.raises(OpenAITimeoutError):
            client.generate_text("挨拶して")

    @patch("integrations.llm.openai_client.get_openai_settings")
    @patch("integrations.llm.openai_client.OpenAI")
    def test_generate_text_connection_error(
        self, mock_openai_class, mock_get_settings, mock_openai_settings
    ):
        """接続エラー時にOpenAIAPIErrorを発生させる."""
        mock_get_settings.return_value = mock_openai_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=Mock()
        )
        mock_openai_class.return_value = mock_client

        client = OpenAIClient()

        with pytest.raises(OpenAIAPIError):
            client.generate_text("挨拶して")


class TestOpenAIClientChatCompletion:
    """OpenAIClientのチャット補完テスト（Function Calling対応）."""

    @pytest.fixture
    def mock_tool_call_response(self):
        """ツール呼び出しを含むモックレスポンス."""
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "get_weather_forecast"
        mock_tool_call.function.arguments = '{"area_code": "130010", "day": 0}'

        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "tool_calls"

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        return mock_response

    @pytest.fixture
    def sample_tools(self):
        """サンプルツール定義."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather_forecast",
                    "description": "天気予報を取得する",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "area_code": {"type": "string"},
                            "day": {"type": "integer"},
                        },
                        "required": ["area_code"],
                    },
                },
            }
        ]

    @patch("integrations.llm.openai_client.get_openai_settings")
    @patch("integrations.llm.openai_client.OpenAI")
    def test_chat_completion_with_tools(
        self,
        mock_openai_class,
        mock_get_settings,
        mock_openai_settings,
        mock_tool_call_response,
        sample_tools,
    ):
        """ツール付きチャット補完が動作する."""
        mock_get_settings.return_value = mock_openai_settings
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_tool_call_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient()
        messages = [{"role": "user", "content": "今日の天気を教えて"}]
        result = client.chat_completion(messages, tools=sample_tools)

        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function.name == "get_weather_forecast"

    @patch("integrations.llm.openai_client.get_openai_settings")
    @patch("integrations.llm.openai_client.OpenAI")
    def test_chat_completion_without_tools(
        self, mock_openai_class, mock_get_settings, mock_openai_settings
    ):
        """ツールなしのチャット補完が動作する."""
        mock_get_settings.return_value = mock_openai_settings
        mock_message = Mock()
        mock_message.content = "今日は晴れです。"
        mock_message.tool_calls = None

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient()
        messages = [{"role": "user", "content": "こんにちは"}]
        result = client.chat_completion(messages)

        assert result.content == "今日は晴れです。"
        assert result.tool_calls is None
