"""Devil's Advocate Agent のテスト."""

import json
from unittest.mock import MagicMock, patch

import pytest

from features.hn_agent.agents.devils_advocate import DevilsAdvocateAgent
from features.hn_agent.models import HNThread, HNThreadSnapshot
from integrations.hn.client import HNComment

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    """Langfuse 接続を外して resolve_prompt を fallback_text 経由にする."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.mark.integration
class TestDevilsAdvocateAgent:
    """DevilsAdvocateAgent のテスト."""

    MOCK_ANALYSIS_JSON = json.dumps(
        {
            "concerns": [
                "スケーラビリティに対する懸念",
                "運用コストが不透明",
            ],
            "past_cases": [
                {
                    "name": "過去の類似技術",
                    "lesson": "ベンダーロックインで移行困難になった",
                }
            ],
            "critical_comments": [
                {
                    "author": "grumpy_dev",
                    "quote": "銀の弾丸ではない",
                    "angle": "運用コスト",
                }
            ],
            "summary": "辛口視点での総括",
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
                author="grumpy_dev",
                text="This is overhyped.",
                parent_id=None,
                children=[],
            ),
        ]
        client.get_comments.return_value = comments
        client.flatten_comments.return_value = comments
        return client

    def test_analyze_returns_structured_output(
        self, mock_llm_client, mock_hn_client, hn_agent_config
    ):
        """構造化JSONが返される."""
        thread = HNThread.objects.create(
            hn_id=900,
            title="Show HN: New Framework",
            url="https://example.com/framework",
            author="maker1",
        )
        HNThreadSnapshot.objects.create(thread=thread, score=300, num_comments=80)

        agent = DevilsAdvocateAgent(
            llm_client=mock_llm_client,
            hn_client=mock_hn_client,
        )
        result = agent.analyze(thread)

        assert result["thread_hn_id"] == 900
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["concerns"] == [
            "スケーラビリティに対する懸念",
            "運用コストが不透明",
        ]
        assert len(result["analysis"]["critical_comments"]) == 1
        assert result["comments_analyzed"] == 1

    def test_analyze_fallback_when_invalid_json(self, mock_hn_client, hn_agent_config):
        """LLM 応答が JSON でないときフォールバック dict を返す."""
        bad_llm = MagicMock()
        bad_llm.generate_text.return_value = "これはJSONではありません"

        thread = HNThread.objects.create(hn_id=901, title="Invalid Thread", author="x")

        agent = DevilsAdvocateAgent(llm_client=bad_llm, hn_client=mock_hn_client)
        result = agent.analyze(thread)

        assert isinstance(result["analysis"], dict)
        assert "concerns" in result["analysis"]
        assert "critical_comments" in result["analysis"]
        assert result["analysis"]["concerns"] == []

    def test_format_comments_section_with_text(self, mock_llm_client, mock_hn_client):
        """コメントがある場合はヘッダと内容が含まれる."""
        agent = DevilsAdvocateAgent(
            llm_client=mock_llm_client, hn_client=mock_hn_client
        )
        section = agent._format_comments_section("[user1]: Hello")

        assert "## HNコメント（抜粋）" in section
        assert "<hn_comments>" in section
        assert "[user1]: Hello" in section

    def test_format_comments_section_empty(self, mock_llm_client, mock_hn_client):
        """コメントが空の場合は空文字を返す."""
        agent = DevilsAdvocateAgent(
            llm_client=mock_llm_client, hn_client=mock_hn_client
        )
        assert agent._format_comments_section("") == ""
