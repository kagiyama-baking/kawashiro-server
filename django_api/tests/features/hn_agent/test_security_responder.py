"""Security Responder Agent のテスト."""

import json
from unittest.mock import MagicMock, patch

import pytest

from features.hn_agent.agents.security_responder import SecurityResponderAgent
from features.hn_agent.models import HNThread, HNThreadSnapshot
from integrations.hn.client import HNComment


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    """Langfuse 接続を外して resolve_prompt を fallback_text 経由にする."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.mark.integration
class TestSecurityResponderAgent:
    """SecurityResponderAgent のテスト."""

    MOCK_ANALYSIS_JSON = json.dumps(
        {
            "cve_ids": ["CVE-2025-12345"],
            "affected": ["example-lib 1.0 〜 1.5"],
            "workarounds": ["設定ファイルで foo オプションを false にする"],
            "official_patch": {
                "available": True,
                "version": "1.6.0 以降",
                "url": "https://example.com/advisory",
            },
            "severity": "high",
            "summary": "1.6.0 にアップグレードするか、回避策を適用する。",
        },
        ensure_ascii=False,
    )

    @pytest.fixture
    def mock_llm_client(self):
        """モックLLMクライアント."""
        client = MagicMock()
        client.generate_text.return_value = self.MOCK_ANALYSIS_JSON
        return client

    @pytest.fixture
    def mock_hn_client(self):
        """モックHNクライアント."""
        client = MagicMock()
        comments = [
            HNComment(
                hn_id=1,
                author="sec_expert",
                text="Patch your systems now.",
                parent_id=None,
                children=[],
            ),
        ]
        client.get_comments.return_value = comments
        client.flatten_comments.return_value = comments
        return client

    @pytest.fixture
    def mock_tavily_client(self):
        """モックTavilyクライアント."""
        from integrations.tavily.client import TavilySearchResult

        client = MagicMock()
        client.search_context.return_value = [
            TavilySearchResult(
                title="Advisory",
                url="https://example.com/advisory",
                content="Details about the patch.",
                score=0.95,
            )
        ]
        return client

    def test_analyze_returns_structured_output(
        self,
        mock_llm_client,
        mock_hn_client,
        mock_tavily_client,
        hn_agent_config,
    ):
        """構造化JSONが返される."""
        thread = HNThread.objects.create(
            hn_id=950,
            title="CVE-2025-12345: example-lib RCE",
            url="https://example.com/cve",
            author="secresearcher",
        )
        HNThreadSnapshot.objects.create(thread=thread, score=500, num_comments=120)

        agent = SecurityResponderAgent(
            llm_client=mock_llm_client,
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        result = agent.analyze(thread)

        assert result["thread_hn_id"] == 950
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["cve_ids"] == ["CVE-2025-12345"]
        assert result["analysis"]["severity"] == "high"
        assert result["analysis"]["official_patch"]["available"] is True
        assert len(result["search_sources"]) == 1

    def test_analyze_without_tavily(
        self, mock_llm_client, mock_hn_client, hn_agent_config
    ):
        """Tavily 未設定でも動作する."""
        thread = HNThread.objects.create(hn_id=951, title="Hack incident", author="x")

        agent = SecurityResponderAgent(
            llm_client=mock_llm_client,
            hn_client=mock_hn_client,
            tavily_client=None,
        )
        with patch.object(
            type(agent),
            "tavily_client",
            new_callable=lambda: property(lambda s: None),
        ):
            result = agent.analyze(thread)

        assert result["search_sources"] == []
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["severity"] == "high"

    def test_analyze_fallback_parsing(
        self, mock_hn_client, mock_tavily_client, hn_agent_config
    ):
        """JSON 以外の応答でフォールバック dict を返す."""
        bad_llm = MagicMock()
        bad_llm.generate_text.return_value = "これはJSONではありません"

        thread = HNThread.objects.create(
            hn_id=952, title="Invalid response", author="y"
        )

        agent = SecurityResponderAgent(
            llm_client=bad_llm,
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        result = agent.analyze(thread)

        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["severity"] == "unknown"
        assert result["analysis"]["cve_ids"] == []

    def test_search_security_context_tavily_error_returns_empty(
        self, mock_llm_client, mock_hn_client
    ):
        """Tavily エラー時は空リストを返しクラッシュしない."""
        from integrations.tavily.exceptions import TavilyError

        tavily = MagicMock()
        tavily.search_context.side_effect = TavilyError("network error")

        agent = SecurityResponderAgent(
            llm_client=mock_llm_client,
            hn_client=mock_hn_client,
            tavily_client=tavily,
        )
        thread = HNThread.objects.create(
            hn_id=954, title="zero-day exploit", author="z"
        )
        assert agent._search_security_context(thread) == []

    def test_search_security_context_query_contains_security_keywords(
        self, mock_llm_client, mock_hn_client, mock_tavily_client
    ):
        """Tavily クエリにセキュリティキーワードが含まれる."""
        agent = SecurityResponderAgent(
            llm_client=mock_llm_client,
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        thread = HNThread.objects.create(
            hn_id=953, title="example-lib vulnerability", author="z"
        )

        agent._search_security_context(thread)

        mock_tavily_client.search_context.assert_called_once()
        call_args = mock_tavily_client.search_context.call_args
        query = call_args[0][0] if call_args[0] else call_args.kwargs.get("query", "")
        assert "example-lib" in query
        assert any(kw in query for kw in ["CVE", "patch", "advisory"])
