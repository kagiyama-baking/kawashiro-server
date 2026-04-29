"""Reporterのテスト."""

from unittest.mock import MagicMock, Mock

import pytest

from features.hn_agent.reporter import (
    Reporter,
    _escape_mrkdwn,
    _sanitize_url,
    _truncate,
)
from integrations.slack.exceptions import SlackError

pytestmark = pytest.mark.django_db


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


@pytest.mark.unit
class TestReporterDevilsAdvocate:
    """Devil's Advocate 通知のテスト."""

    @pytest.fixture
    def mock_slack_client(self):
        client = MagicMock()
        response = Mock()
        response.status_code = 200
        client.send_blocks.return_value = response
        return client

    @pytest.fixture
    def devils_result(self):
        return {
            "thread_hn_id": 200,
            "thread_title": "Show HN: New Framework",
            "thread_url": "https://example.com/framework",
            "score_info": "スコア: 300, コメント数: 80",
            "analysis": {
                "concerns": [
                    "スケーラビリティへの懸念",
                    "運用コストが不透明",
                ],
                "past_cases": [
                    {
                        "name": "類似技術X",
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
            "comments_analyzed": 10,
        }

    def test_report_devils_advocate_sends_blocks(
        self, mock_slack_client, devils_result
    ):
        """辛口レポートがブロックで送信される."""
        reporter = Reporter(slack_client=mock_slack_client)
        assert reporter.report_devils_advocate(devils_result) is True

        mock_slack_client.send_blocks.assert_called_once()
        blocks = mock_slack_client.send_blocks.call_args.kwargs["blocks"]
        # ヘッダー + 記事リンク + 懸念点 + 過去事例 + 辛口コメント + 総括 の最小構成
        assert len(blocks) >= 5
        # ヘッダーに「辛口」が含まれる
        header_text = blocks[0]["text"]["text"]
        assert "HN民の辛口な意見" in header_text
        # 懸念点の section が存在する
        serialized = "".join(
            b.get("text", {}).get("text", "") for b in blocks if b.get("text")
        )
        assert "懸念点" in serialized
        assert "スケーラビリティへの懸念" in serialized

    def test_report_devils_advocate_without_slack_returns_false(self, devils_result):
        reporter = Reporter(slack_client=None)
        reporter._slack_client = None
        assert reporter.report_devils_advocate(devils_result) is False

    def test_report_devils_advocate_slack_error_returns_false(
        self, mock_slack_client, devils_result
    ):
        """Slack エラー時は False を返す."""
        mock_slack_client.send_blocks.side_effect = SlackError("boom")
        reporter = Reporter(slack_client=mock_slack_client)
        assert reporter.report_devils_advocate(devils_result) is False


@pytest.mark.unit
class TestReporterSecurityResponder:
    """Security Responder 通知のテスト."""

    @pytest.fixture
    def mock_slack_client(self):
        client = MagicMock()
        response = Mock()
        response.status_code = 200
        client.send_blocks.return_value = response
        return client

    @pytest.fixture
    def security_result(self):
        return {
            "thread_hn_id": 300,
            "thread_title": "CVE-2025-12345: example-lib RCE",
            "thread_url": "https://example.com/cve",
            "score_info": "スコア: 500, コメント数: 120",
            "analysis": {
                "cve_ids": ["CVE-2025-12345"],
                "affected": ["example-lib 1.0 〜 1.5"],
                "workarounds": ["foo オプションを false にする"],
                "official_patch": {
                    "available": True,
                    "version": "1.6.0 以降",
                    "url": "https://example.com/advisory",
                },
                "severity": "critical",
                "summary": "直ちに 1.6.0 以降にアップグレードする。",
            },
            "search_sources": [
                {
                    "title": "Advisory",
                    "url": "https://example.com/advisory",
                    "content": "詳細",
                }
            ],
            "comments_analyzed": 20,
        }

    def test_report_security_responder_sends_blocks(
        self, mock_slack_client, security_result
    ):
        """セキュリティレポートがブロックで送信される."""
        reporter = Reporter(slack_client=mock_slack_client)
        assert reporter.report_security_responder(security_result) is True

        mock_slack_client.send_blocks.assert_called_once()
        blocks = mock_slack_client.send_blocks.call_args.kwargs["blocks"]
        assert len(blocks) >= 5

        header_text = blocks[0]["text"]["text"]
        assert "セキュリティインシデント詳細" in header_text

        serialized = "".join(
            b.get("text", {}).get("text", "") for b in blocks if b.get("text")
        )
        assert "CVE-2025-12345" in serialized
        assert "example-lib 1.0 〜 1.5" in serialized
        assert "1.6.0 以降" in serialized

    def test_report_security_responder_no_patch_available(
        self, mock_slack_client, security_result
    ):
        """公式パッチ未リリース時は未リリース文言が含まれる."""
        security_result["analysis"]["official_patch"] = {
            "available": False,
            "version": None,
            "url": None,
        }
        reporter = Reporter(slack_client=mock_slack_client)
        reporter.report_security_responder(security_result)

        blocks = mock_slack_client.send_blocks.call_args.kwargs["blocks"]
        serialized = "".join(
            b.get("text", {}).get("text", "") for b in blocks if b.get("text")
        )
        assert "未リリース" in serialized

    def test_report_security_responder_without_slack_returns_false(
        self, security_result
    ):
        reporter = Reporter(slack_client=None)
        reporter._slack_client = None
        assert reporter.report_security_responder(security_result) is False

    def test_report_security_responder_slack_error_returns_false(
        self, mock_slack_client, security_result
    ):
        """Slack エラー時は False を返す."""
        mock_slack_client.send_blocks.side_effect = SlackError("boom")
        reporter = Reporter(slack_client=mock_slack_client)
        assert reporter.report_security_responder(security_result) is False

    def test_report_security_responder_sanitizes_malicious_patch_url(
        self, mock_slack_client, security_result
    ):
        """official_patch.url が危険な値の場合、リンクが出力されない."""
        security_result["analysis"]["official_patch"]["url"] = "javascript:alert(1)"
        reporter = Reporter(slack_client=mock_slack_client)
        reporter.report_security_responder(security_result)

        blocks = mock_slack_client.send_blocks.call_args.kwargs["blocks"]
        serialized = "".join(
            b.get("text", {}).get("text", "") for b in blocks if b.get("text")
        )
        assert "javascript:" not in serialized


class TestSanitizeUrl:
    """_sanitize_url のテスト."""

    def test_allows_https(self):
        assert _sanitize_url("https://example.com/p") == "https://example.com/p"

    def test_allows_http(self):
        assert _sanitize_url("http://example.com/p") == "http://example.com/p"

    def test_rejects_javascript_scheme(self):
        assert _sanitize_url("javascript:alert(1)") is None

    def test_rejects_data_scheme(self):
        assert _sanitize_url("data:text/html,<script>alert(1)</script>") is None

    def test_rejects_pipe_character(self):
        assert _sanitize_url("https://example.com/|injected") is None

    def test_rejects_angle_brackets(self):
        assert _sanitize_url("https://example.com/<foo>") is None

    def test_rejects_newline(self):
        assert _sanitize_url("https://example.com/\nevil") is None

    def test_none_returns_none(self):
        assert _sanitize_url(None) is None

    def test_empty_returns_none(self):
        assert _sanitize_url("") is None


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
