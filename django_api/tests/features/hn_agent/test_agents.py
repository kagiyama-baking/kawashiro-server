"""Detective Agentのテスト."""

import json
from unittest.mock import MagicMock, patch

import pytest

from features.hn_agent.agents.detective import DetectiveAgent
from features.hn_agent.models import HNThread, HNThreadSnapshot
from integrations.hn.client import HNComment


@pytest.mark.integration
class TestDetectiveAgent:
    """DetectiveAgentのテスト."""

    MOCK_ANALYSIS_JSON = json.dumps(
        {
            "title_ja": "テスト記事タイトル",
            "why_trending": "技術的に面白い内容のため。",
            "background": "著者はテスト分野の専門家。",
            "comment_highlights": [
                {
                    "author": "user1",
                    "quote": "素晴らしい記事だ",
                    "stance": "肯定",
                }
            ],
            "summary": "技術的関心が高い。",
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
                author="user1",
                text="Great article!",
                parent_id=None,
                children=[],
            ),
            HNComment(
                hn_id=2,
                author="user2",
                text="I disagree with this approach.",
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
                title="Background Info",
                url="https://example.com/bg",
                content="Some background context about the topic.",
                score=0.9,
            )
        ]
        return client

    def test_investigate_completes_and_marks_thread(
        self, mock_llm_client, mock_hn_client, mock_tavily_client
    ):
        """調査が完了しスレッドが調査済みになる."""
        thread = HNThread.objects.create(
            hn_id=600,
            title="Hot Thread",
            url="https://example.com/hot",
            author="author1",
        )
        HNThreadSnapshot.objects.create(thread=thread, score=200, num_comments=50)

        agent = DetectiveAgent(
            llm_client=mock_llm_client,
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        result = agent.investigate(thread)

        assert result["thread_hn_id"] == 600
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["title_ja"] == "テスト記事タイトル"
        assert result["comments_analyzed"] == 2
        assert len(result["background_sources"]) == 1

        thread.refresh_from_db()
        assert thread.is_investigated is True

    def test_investigate_without_tavily(self, mock_llm_client, mock_hn_client):
        """Tavily未設定でも調査が完了する."""
        thread = HNThread.objects.create(
            hn_id=601, title="No Tavily Thread", author="author2"
        )

        agent = DetectiveAgent(
            llm_client=mock_llm_client,
            hn_client=mock_hn_client,
            tavily_client=None,
        )
        # tavily_clientプロパティがNoneを返すようにする
        with patch.object(
            type(agent), "tavily_client", new_callable=lambda: property(lambda s: None)
        ):
            result = agent.investigate(thread)

        assert result["background_sources"] == []
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["title_ja"] == "テスト記事タイトル"

    def test_build_analysis_prompt_includes_all_sections(
        self, mock_llm_client, mock_hn_client
    ):
        """分析プロンプトに全セクションが含まれる."""
        thread = HNThread.objects.create(
            hn_id=602, title="Prompt Test", url="https://example.com", author="test"
        )

        agent = DetectiveAgent(llm_client=mock_llm_client, hn_client=mock_hn_client)

        prompt = agent._build_analysis_prompt(
            thread=thread,
            score_info="スコア: 100, コメント数: 50",
            comments_text="[user1]: Hello",
            background=[
                {
                    "title": "BG",
                    "url": "https://bg.com",
                    "content": "background",
                }
            ],
        )

        assert "Prompt Test" in prompt
        assert "スコア: 100" in prompt
        assert "Hello" in prompt
        assert "BG" in prompt
