"""Hypothesis Agentのテスト."""

import json
from unittest.mock import MagicMock, patch

import pytest

from features.hn_agent.agents.hypothesis import HypothesisAgent
from features.hn_agent.models import HNThread, Investigation
from integrations.hn.client import HNComment


@pytest.mark.integration
class TestHypothesisAgent:
    """HypothesisAgentのテスト."""

    @pytest.fixture
    def thread(self):
        """テスト用スレッド."""
        return HNThread.objects.create(
            hn_id=900,
            title="Controversial Topic",
            url="https://example.com/debate",
            author="debater",
        )

    @pytest.fixture
    def mock_openai_client(self):
        """モックOpenAIクライアント."""
        client = MagicMock()
        return client

    @pytest.fixture
    def mock_hn_client(self):
        """モックHNクライアント."""
        client = MagicMock()
        comments = [
            HNComment(
                hn_id=1,
                author="user1",
                text="Rust is clearly better than Go for systems programming.",
                parent_id=None,
                children=[],
            ),
            HNComment(
                hn_id=2,
                author="user2",
                text="Go's simplicity makes it superior for production systems.",
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
                title="Evidence",
                url="https://example.com/evidence",
                content="Supporting evidence text.",
                score=0.9,
            )
        ]
        return client

    def test_investigate_with_claims(
        self, thread, mock_openai_client, mock_hn_client, mock_tavily_client
    ):
        """対立主張を検出・検証して結果を保存する."""
        # extract_claimsの応答
        claims_json = json.dumps(
            {
                "claims": [
                    {
                        "claim_a": "Rustはシステムプログラミングに最適",
                        "claim_b": "Goのシンプルさが本番環境に向いている",
                        "topic": "Rust vs Go",
                    }
                ]
            }
        )
        # generate_textの応答: 1回目=claims抽出、2回目=verdict
        mock_openai_client.generate_text.side_effect = [
            claims_json,
            "結論: 用途によって異なる。",
        ]

        agent = HypothesisAgent(
            openai_client=mock_openai_client,
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        result = agent.investigate(thread)

        assert result["has_claims"] is True
        assert result["claims_found"] == 1
        assert len(result["verdicts"]) == 1
        assert result["verdicts"][0]["topic"] == "Rust vs Go"
        assert result["verdicts"][0]["verdict"] == "結論: 用途によって異なる。"
        assert Investigation.objects.filter(
            thread=thread, agent_type="hypothesis"
        ).exists()

    def test_investigate_no_claims(self, thread, mock_openai_client, mock_hn_client):
        """対立主張がない場合."""
        mock_openai_client.generate_text.return_value = json.dumps({"claims": []})

        agent = HypothesisAgent(
            openai_client=mock_openai_client,
            hn_client=mock_hn_client,
        )
        result = agent.investigate(thread)

        assert result["has_claims"] is False
        assert result["claims_found"] == 0
        assert Investigation.objects.filter(
            thread=thread, agent_type="hypothesis"
        ).exists()

    def test_investigate_no_comments(self, thread, mock_openai_client, mock_hn_client):
        """コメントがない場合."""
        mock_hn_client.get_comments.return_value = []
        mock_hn_client.flatten_comments.return_value = []

        agent = HypothesisAgent(
            openai_client=mock_openai_client,
            hn_client=mock_hn_client,
        )
        result = agent.investigate(thread)

        assert result["has_claims"] is False
        assert "コメントが見つかりませんでした" in result["reason"]

    def test_extract_claims_invalid_json(
        self, thread, mock_openai_client, mock_hn_client
    ):
        """LLMがJSON以外を返した場合."""
        mock_openai_client.generate_text.return_value = "これはJSONではありません"

        agent = HypothesisAgent(
            openai_client=mock_openai_client,
            hn_client=mock_hn_client,
        )
        result = agent.investigate(thread)

        assert result["has_claims"] is False

    def test_investigate_without_tavily(
        self, thread, mock_openai_client, mock_hn_client
    ):
        """Tavily未設定でも動作する."""
        claims_json = json.dumps(
            {
                "claims": [
                    {
                        "claim_a": "A is better",
                        "claim_b": "B is better",
                        "topic": "A vs B",
                    }
                ]
            }
        )
        mock_openai_client.generate_text.side_effect = [
            claims_json,
            "根拠なしで判断保留。",
        ]

        agent = HypothesisAgent(
            openai_client=mock_openai_client,
            hn_client=mock_hn_client,
            tavily_client=None,
        )
        with patch.object(
            type(agent), "tavily_client", new_callable=lambda: property(lambda s: None)
        ):
            result = agent.investigate(thread)

        assert result["has_claims"] is True
        assert result["verdicts"][0]["evidence_a"] == []
        assert result["verdicts"][0]["evidence_b"] == []
