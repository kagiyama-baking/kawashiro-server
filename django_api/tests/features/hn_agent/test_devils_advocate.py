"""Devil's Advocate Agent のテスト."""

import json
from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import async_to_sync

from features.hn_agent.agents.devils_advocate import (
    DEVILS_ADVOCATE_AGENT,
    DevilsAdvocateAgent,
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
def advocate_llm(hn_llm_services):
    """Devil's Advocate の LLM 応答を台本で固定する."""
    llm = ScriptedLLM()
    with DEVILS_ADVOCATE_AGENT.override(model=llm.model):
        yield llm


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
        self, mock_hn_client, advocate_llm, hn_agent_config
    ):
        """構造化JSONが返される."""
        advocate_llm.enqueue(self.MOCK_ANALYSIS_JSON)
        thread = HNThread.objects.create(
            hn_id=900,
            title="Show HN: New Framework",
            url="https://example.com/framework",
            author="maker1",
        )
        HNThreadSnapshot.objects.create(thread=thread, score=300, num_comments=80)

        agent = DevilsAdvocateAgent(hn_client=mock_hn_client)
        result = async_to_sync(agent.analyze)(thread)

        assert result["thread_hn_id"] == 900
        assert result["thread_url"] == "https://example.com/framework"
        assert result["score_info"] == "スコア: 300, コメント数: 80"
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["concerns"] == [
            "スケーラビリティに対する懸念",
            "運用コストが不透明",
        ]
        assert len(result["analysis"]["critical_comments"]) == 1
        assert result["comments_analyzed"] == 1

    def test_analyze_prompt_contains_uncommitted_data(
        self, mock_hn_client, advocate_llm, hn_agent_config
    ):
        """準備処理は呼び出し元の DB 接続で動き、未コミットのデータがプロンプトに入る."""
        advocate_llm.enqueue(self.MOCK_ANALYSIS_JSON)
        thread = HNThread.objects.create(hn_id=902, title="Uncommitted", author="x")
        HNThreadSnapshot.objects.create(thread=thread, score=123, num_comments=45)

        agent = DevilsAdvocateAgent(hn_client=mock_hn_client)
        async_to_sync(agent.analyze)(thread)

        request = advocate_llm.requests[0]
        assert "スコア: 123, コメント数: 45" in request.user_prompt
        assert "[grumpy_dev]: This is overhyped." in request.user_prompt
        assert (
            request.instructions
            == hn_agent_config.devils_advocate_system_prompt.fallback_text
        )
        metadata = request.model_settings["extra_body"]["metadata"]
        assert metadata["service_name"] == "devils_advocate"

    def test_analyze_fallback_when_invalid_json(
        self, mock_hn_client, advocate_llm, hn_agent_config
    ):
        """LLM 応答が JSON でないときフォールバック dict を返す."""
        advocate_llm.enqueue("これはJSONではありません", "これもJSONではありません")

        thread = HNThread.objects.create(hn_id=901, title="Invalid Thread", author="x")

        agent = DevilsAdvocateAgent(hn_client=mock_hn_client)
        result = async_to_sync(agent.analyze)(thread)

        assert result["analysis"] == {
            "concerns": [],
            "past_cases": [],
            "critical_comments": [],
            "summary": "これもJSONではありません",
        }
        assert len(advocate_llm.requests) == 2

    def test_analyze_missing_required_key_returns_fallback(
        self, mock_hn_client, advocate_llm, hn_agent_config
    ):
        """必須キーのない JSON はフォールバックにする（従来の検査と同じ）."""
        no_required = json.dumps({"concerns": ["懸念"]}, ensure_ascii=False)
        advocate_llm.enqueue(no_required, no_required)
        thread = HNThread.objects.create(hn_id=903, title="Missing", author="x")

        agent = DevilsAdvocateAgent(hn_client=mock_hn_client)
        result = async_to_sync(agent.analyze)(thread)

        assert result["analysis"]["concerns"] == []
        assert result["analysis"]["summary"] == no_required

    def test_format_comments_section_with_text(self, mock_hn_client):
        """コメントがある場合はヘッダと内容が含まれる."""
        agent = DevilsAdvocateAgent(hn_client=mock_hn_client)
        section = agent._format_comments_section("[user1]: Hello")

        assert "## HNコメント（抜粋）" in section
        assert "<hn_comments>" in section
        assert "[user1]: Hello" in section

    def test_format_comments_section_empty(self, mock_hn_client):
        """コメントが空の場合は空文字を返す."""
        agent = DevilsAdvocateAgent(hn_client=mock_hn_client)
        assert agent._format_comments_section("") == ""
