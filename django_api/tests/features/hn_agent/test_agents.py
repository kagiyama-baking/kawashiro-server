"""Memory Agent / Detective Agentのテスト."""

import json
from unittest.mock import MagicMock, patch

import pytest

from features.hn_agent.agents.detective import DetectiveAgent
from features.hn_agent.agents.memory import MemoryAgent
from features.hn_agent.models import HNThread, HNThreadSnapshot, Investigation
from integrations.hn.client import HNComment


@pytest.mark.integration
class TestMemoryAgent:
    """MemoryAgentのテスト."""

    @pytest.fixture
    def mock_openai_client(self):
        """モックOpenAIクライアント."""
        client = MagicMock()
        client.generate_embedding.return_value = [0.1] * 1536
        return client

    def test_ensure_embedding_creates_new(self, mock_openai_client):
        """embeddingがない場合に新規作成する."""
        thread = HNThread.objects.create(
            hn_id=500, title="Test Thread", url="https://example.com"
        )
        agent = MemoryAgent(openai_client=mock_openai_client)

        embedding = agent.ensure_embedding(thread)

        assert embedding.thread == thread
        assert len(embedding.embedding) == 1536

    def test_ensure_embedding_returns_existing(self, mock_openai_client):
        """既存embeddingがある場合はそれを返す."""
        from features.hn_agent.models import ThreadEmbedding

        thread = HNThread.objects.create(hn_id=501, title="Test")
        ThreadEmbedding.objects.create(thread=thread, embedding=[0.5] * 1536)

        agent = MemoryAgent(openai_client=mock_openai_client)
        embedding = agent.ensure_embedding(thread)

        # OpenAI APIは呼ばれない
        mock_openai_client.generate_embedding.assert_not_called()
        assert embedding.thread == thread

    @patch.object(MemoryAgent, "find_similar_threads", return_value=[])
    def test_investigate_creates_investigation(self, _mock_find, mock_openai_client):
        """調査結果がInvestigationに保存される."""
        thread = HNThread.objects.create(hn_id=502, title="Test Investigation")
        agent = MemoryAgent(openai_client=mock_openai_client)

        result = agent.investigate(thread)

        assert result["thread_hn_id"] == 502
        assert result["has_similar"] is False
        assert Investigation.objects.filter(thread=thread, agent_type="memory").exists()

    @patch.object(
        MemoryAgent,
        "find_similar_threads",
        return_value=[
            {
                "hn_id": 999,
                "title": "Past Similar Thread",
                "url": "https://example.com/past",
                "similarity": 0.92,
                "first_seen": "2026-01-01T00:00:00+00:00",
                "was_investigated": True,
            }
        ],
    )
    def test_investigate_finds_similar_threads(self, _mock_find, mock_openai_client):
        """類似スレッドが見つかった場合の結果構造を検証する."""
        thread = HNThread.objects.create(hn_id=503, title="Test Similar")
        agent = MemoryAgent(openai_client=mock_openai_client)

        result = agent.investigate(thread)

        assert result["has_similar"] is True
        assert len(result["similar_threads"]) == 1
        assert result["similar_threads"][0]["hn_id"] == 999
        assert "見つかりました" in result["summary"]

    def test_build_summary_no_similar(self, mock_openai_client):
        """類似なしのサマリーを生成する."""
        thread = HNThread.objects.create(hn_id=504, title="No Similar")
        agent = MemoryAgent(openai_client=mock_openai_client)

        summary = agent._build_summary(thread, [])

        assert "見つかりませんでした" in summary


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
    def mock_openai_client(self):
        """モックOpenAIクライアント."""
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

    def test_investigate_creates_investigation(
        self, mock_openai_client, mock_hn_client, mock_tavily_client
    ):
        """調査結果がInvestigationに保存される."""
        thread = HNThread.objects.create(
            hn_id=600,
            title="Hot Thread",
            url="https://example.com/hot",
            author="author1",
        )
        HNThreadSnapshot.objects.create(thread=thread, score=200, num_comments=50)

        agent = DetectiveAgent(
            openai_client=mock_openai_client,
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )
        result = agent.investigate(thread)

        assert result["thread_hn_id"] == 600
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["title_ja"] == "テスト記事タイトル"
        assert result["comments_analyzed"] == 2
        assert len(result["background_sources"]) == 1
        assert Investigation.objects.filter(
            thread=thread, agent_type="detective"
        ).exists()

        # スレッドが調査済みになる
        thread.refresh_from_db()
        assert thread.is_investigated is True

    def test_investigate_without_tavily(self, mock_openai_client, mock_hn_client):
        """Tavily未設定でも調査が完了する."""
        thread = HNThread.objects.create(
            hn_id=601, title="No Tavily Thread", author="author2"
        )

        agent = DetectiveAgent(
            openai_client=mock_openai_client,
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
        self, mock_openai_client, mock_hn_client
    ):
        """分析プロンプトに全セクションが含まれる."""
        thread = HNThread.objects.create(
            hn_id=602, title="Prompt Test", url="https://example.com", author="test"
        )

        agent = DetectiveAgent(
            openai_client=mock_openai_client, hn_client=mock_hn_client
        )

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
