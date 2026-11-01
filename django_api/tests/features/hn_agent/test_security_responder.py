"""Security Responder Agent のテスト."""

import json
from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import async_to_sync

from features.hn_agent.agents.security_responder import (
    SECURITY_RESPONDER_AGENT,
    SecurityResponderAgent,
)
from features.hn_agent.models import HNThread, HNThreadSnapshot
from integrations.hn.client import HNComment
from tests.fixtures.llm import ScriptedLLM

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    """Langfuse 接続を外して resolve_prompt を fallback_text 経由にする."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.fixture
def security_llm(hn_llm_services):
    """Security Responder の LLM 応答を台本で固定する."""
    llm = ScriptedLLM()
    with SECURITY_RESPONDER_AGENT.override(model=llm.model):
        yield llm


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
        mock_hn_client,
        mock_tavily_client,
        security_llm,
        hn_agent_config,
    ):
        """構造化JSONが返される."""
        security_llm.enqueue(self.MOCK_ANALYSIS_JSON)
        thread = HNThread.objects.create(
            hn_id=950,
            title="CVE-2025-12345: example-lib RCE",
            url="https://example.com/cve",
            author="secresearcher",
        )
        HNThreadSnapshot.objects.create(thread=thread, score=500, num_comments=120)

        agent = SecurityResponderAgent(
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        result = async_to_sync(agent.analyze)(thread)

        assert result["thread_hn_id"] == 950
        assert result["thread_url"] == "https://example.com/cve"
        assert result["score_info"] == "スコア: 500, コメント数: 120"
        assert result["comments_analyzed"] == 1
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["cve_ids"] == ["CVE-2025-12345"]
        assert result["analysis"]["severity"] == "high"
        assert result["analysis"]["official_patch"]["available"] is True
        assert len(result["search_sources"]) == 1

    def test_analyze_prompt_contains_uncommitted_data(
        self,
        mock_hn_client,
        mock_tavily_client,
        security_llm,
        hn_agent_config,
    ):
        """準備処理は呼び出し元の DB 接続で動き、未コミットのデータがプロンプトに入る."""
        security_llm.enqueue(self.MOCK_ANALYSIS_JSON)
        thread = HNThread.objects.create(hn_id=955, title="Uncommitted", author="x")
        HNThreadSnapshot.objects.create(thread=thread, score=321, num_comments=54)

        agent = SecurityResponderAgent(
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        async_to_sync(agent.analyze)(thread)

        request = security_llm.requests[0]
        assert "スコア: 321, コメント数: 54" in request.user_prompt
        assert "[sec_expert]: Patch your systems now." in request.user_prompt
        assert "Details about the patch." in request.user_prompt
        assert (
            request.instructions
            == hn_agent_config.security_responder_system_prompt.fallback_text
        )
        metadata = request.model_settings["extra_body"]["metadata"]
        assert metadata["service_name"] == "security_responder"

    def test_analyze_without_tavily(
        self, mock_hn_client, security_llm, hn_agent_config
    ):
        """Tavily 未設定でも動作する."""
        security_llm.enqueue(self.MOCK_ANALYSIS_JSON)
        thread = HNThread.objects.create(hn_id=951, title="Hack incident", author="x")

        agent = SecurityResponderAgent(hn_client=mock_hn_client, tavily_client=None)
        with patch.object(
            type(agent),
            "tavily_client",
            new_callable=lambda: property(lambda s: None),
        ):
            result = async_to_sync(agent.analyze)(thread)

        assert result["search_sources"] == []
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["severity"] == "high"

    def test_analyze_fallback_parsing(
        self, mock_hn_client, mock_tavily_client, security_llm, hn_agent_config
    ):
        """JSON 以外の応答でフォールバック dict を返す."""
        security_llm.enqueue("これはJSONではありません", "これもJSONではありません")

        thread = HNThread.objects.create(
            hn_id=952, title="Invalid response", author="y"
        )

        agent = SecurityResponderAgent(
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        result = async_to_sync(agent.analyze)(thread)

        assert result["analysis"] == {
            "cve_ids": [],
            "affected": [],
            "workarounds": [],
            "official_patch": {"available": False, "version": None, "url": None},
            "severity": "unknown",
            "summary": "これもJSONではありません",
        }
        assert len(security_llm.requests) == 2

    def test_search_security_context_tavily_error_returns_empty(self, mock_hn_client):
        """Tavily エラー時は空リストを返しクラッシュしない."""
        from integrations.tavily.exceptions import TavilyError

        tavily = MagicMock()
        tavily.search_context.side_effect = TavilyError("network error")

        agent = SecurityResponderAgent(
            hn_client=mock_hn_client,
            tavily_client=tavily,
        )
        thread = HNThread.objects.create(
            hn_id=954, title="zero-day exploit", author="z"
        )
        assert agent._search_security_context(thread) == []

    def test_search_security_context_query_contains_security_keywords(
        self, mock_hn_client, mock_tavily_client
    ):
        """Tavily クエリにセキュリティキーワードが含まれる."""
        agent = SecurityResponderAgent(
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
