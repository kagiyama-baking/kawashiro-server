"""Tavily APIクライアントのテスト."""

from unittest.mock import Mock, patch

import pytest
import requests

from integrations.tavily.client import TavilyClient, TavilySearchResult
from integrations.tavily.config import TavilySettings
from integrations.tavily.exceptions import TavilyAPIError, TavilyConfigurationError


@pytest.fixture
def mock_tavily_settings():
    """Tavily DB設定のモック."""
    settings = TavilySettings(api_key="test-db-key", timeout=30)
    with patch(
        "integrations.tavily.client.get_tavily_settings",
        return_value=settings,
    ):
        yield settings


@pytest.mark.unit
class TestTavilyClient:
    """TavilyClientのテスト."""

    def test_init_without_db_config_raises_error(self):
        """DB設定なしで初期化するとエラーになる."""
        with pytest.raises(TavilyConfigurationError):
            TavilyClient()

    def test_init_with_explicit_api_key(self, mock_tavily_settings):
        """明示的にAPIキーを指定して初期化できる."""
        client = TavilyClient(api_key="explicit-key")
        assert client.api_key == "explicit-key"

    def test_init_falls_back_to_db_settings(self, mock_tavily_settings):
        """引数省略時はDB設定から取得する."""
        client = TavilyClient()
        assert client.api_key == "test-db-key"
        assert client.timeout == 30

    @patch("integrations.tavily.client.requests.post")
    def test_search_returns_raw_response(self, mock_post, mock_tavily_settings):
        """検索結果を辞書で返す."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "content": "Test content",
                    "score": 0.95,
                }
            ],
            "answer": "Test answer",
        }
        mock_post.return_value = mock_response

        client = TavilyClient(api_key="test-key")
        result = client.search("test query")

        assert "results" in result
        assert len(result["results"]) == 1

    @patch("integrations.tavily.client.requests.post")
    def test_search_sends_correct_payload(self, mock_post, mock_tavily_settings):
        """正しいペイロードでAPIを呼び出す."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response

        client = TavilyClient(api_key="test-key")
        client.search("test query", max_results=3, search_depth="advanced")

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["query"] == "test query"
        assert payload["max_results"] == 3
        assert payload["search_depth"] == "advanced"
        assert payload["api_key"] == "test-key"

    @patch("integrations.tavily.client.requests.post")
    def test_search_context_returns_typed_results(
        self, mock_post, mock_tavily_settings
    ):
        """search_contextが型付きの結果を返す."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Result 1",
                    "url": "https://example.com/1",
                    "content": "Content 1",
                    "score": 0.9,
                },
                {
                    "title": "Result 2",
                    "url": "https://example.com/2",
                    "content": "Content 2",
                    "score": 0.8,
                },
            ]
        }
        mock_post.return_value = mock_response

        client = TavilyClient(api_key="test-key")
        results = client.search_context("test query")

        assert len(results) == 2
        assert isinstance(results[0], TavilySearchResult)
        assert results[0].title == "Result 1"
        assert results[0].score == 0.9

    @patch("integrations.tavily.client.requests.post")
    def test_search_network_error_raises_tavily_error(
        self, mock_post, mock_tavily_settings
    ):
        """ネットワークエラー時にTavilyAPIErrorを送出する."""
        mock_post.side_effect = requests.ConnectionError("Connection refused")

        client = TavilyClient(api_key="test-key")

        with pytest.raises(TavilyAPIError, match="失敗しました"):
            client.search("test query")
