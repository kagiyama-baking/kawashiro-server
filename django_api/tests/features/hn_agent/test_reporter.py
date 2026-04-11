"""Reporterのテスト."""

from unittest.mock import MagicMock, Mock

import pytest

from features.hn_agent.reporter import Reporter, _escape_mrkdwn, _truncate


@pytest.mark.unit
class TestReporter:
    """Reporterのテスト."""

    @pytest.fixture
    def mock_slack_client(self):
        """モックSlackクライアント."""
        client = MagicMock()
        mock_response = Mock()
        mock_response.status_code = 200
        client.send_blocks.return_value = mock_response
        return client

    @pytest.fixture
    def detective_result(self):
        """Detective調査結果のサンプル（構造化JSON）."""
        return {
            "thread_hn_id": 100,
            "thread_title": "Test Thread",
            "thread_url": "https://example.com",
            "score_info": "スコア: 200, コメント数: 50",
            "analysis": {
                "title_ja": "テストスレッド",
                "why_trending": "技術的に面白いため注目されている。",
                "background": "著者はテスト分野の専門家。",
                "comment_highlights": [
                    {
                        "author": "user1",
                        "quote": "素晴らしい記事だ",
                        "stance": "肯定",
                    },
                    {
                        "author": "user2",
                        "quote": "もう少し深掘りが必要では",
                        "stance": "批判",
                    },
                ],
                "summary": "技術的関心とコミュニティの反応が重なった結果。",
            },
            "background_sources": [
                {
                    "title": "Background",
                    "url": "https://example.com/bg",
                    "content": "Background info",
                }
            ],
            "comments_analyzed": 10,
        }

    @pytest.fixture
    def detective_result_fallback(self):
        """Detective調査結果のサンプル（プレーンテキスト）."""
        return {
            "thread_hn_id": 100,
            "thread_title": "Test Thread",
            "thread_url": "https://example.com",
            "score_info": "スコア: 200",
            "analysis": "これはプレーンテキスト分析です。",
            "background_sources": [],
            "comments_analyzed": 5,
        }

    def test_report_detective_sends_structured_blocks(
        self, mock_slack_client, detective_result
    ):
        """構造化JSON分析をSlackブロックで送信する."""
        reporter = Reporter(slack_client=mock_slack_client)
        success = reporter.report_detective(detective_result)

        assert success is True
        mock_slack_client.send_blocks.assert_called_once()
        call_kwargs = mock_slack_client.send_blocks.call_args.kwargs
        blocks = call_kwargs["blocks"]
        # ヘッダー + 記事情報 + divider + 注目理由 + 背景 + divider + コメントヘッダー + コメント + divider + 総括 + 参考情報
        assert len(blocks) >= 6
        # ヘッダーに日本語タイトルが含まれる
        assert "テストスレッド" in blocks[0]["text"]["text"]

    def test_report_detective_fallback_text(
        self, mock_slack_client, detective_result_fallback
    ):
        """プレーンテキスト分析でもSlackに送信できる."""
        reporter = Reporter(slack_client=mock_slack_client)
        success = reporter.report_detective(detective_result_fallback)

        assert success is True
        mock_slack_client.send_blocks.assert_called_once()

    def test_report_detective_without_slack_returns_false(self, detective_result):
        """Slack未設定でFalseを返す."""
        reporter = Reporter(slack_client=None)
        reporter._slack_client = None
        success = reporter.report_detective(detective_result)

        assert success is False


class TestTruncate:
    """_truncate関数のテスト."""

    def test_short_text_unchanged(self):
        """短いテキストはそのまま返す."""
        assert _truncate("hello", 10) == "hello"

    def test_long_text_truncated(self):
        """長いテキストは切り詰める."""
        result = _truncate("a" * 100, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_exact_length_unchanged(self):
        """ちょうどの長さはそのまま返す."""
        text = "a" * 50
        assert _truncate(text, 50) == text


class TestEscapeMrkdwn:
    """_escape_mrkdwn関数のテスト."""

    def test_escape_angle_brackets(self):
        """<>がエスケープされる."""
        assert _escape_mrkdwn("<script>") == "&lt;script&gt;"

    def test_escape_ampersand(self):
        """&がエスケープされる."""
        assert _escape_mrkdwn("A & B") == "A &amp; B"

    def test_no_double_escape(self):
        """二重エスケープされない."""
        assert _escape_mrkdwn("&amp;") == "&amp;amp;"
