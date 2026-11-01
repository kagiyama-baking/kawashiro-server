"""サブエージェントの出力スキーマのテスト."""

import pytest
from pydantic import ValidationError

from features.hn_agent.agents.schemas import (
    DetectiveAnalysis,
    DevilsAdvocateAnalysis,
    SecurityAnalysis,
)
from features.hn_agent.reporter import Reporter

HN_URL = "https://news.ycombinator.com/item?id=1"
THREAD_RESULT = {"thread_title": "Title", "score_info": "スコア: 1"}


def _dump(schema, **data) -> dict:
    """`run_analysis` と同じ形で dict にする."""
    return schema.model_validate(data).model_dump(mode="json", exclude_unset=True)


def _reporter() -> Reporter:
    """ブロックの組み立てだけを確かめるので Slack クライアントは使わない."""
    return Reporter(slack_client=object())


@pytest.mark.unit
class TestDetectiveAnalysis:
    """DetectiveAnalysis のテスト."""

    def test_required_keys_only_is_valid_and_adds_no_keys(self):
        """必須キーだけで通り、LLM が返していないキーを足さない."""
        assert _dump(DetectiveAnalysis, title_ja="題", comment_highlights=[]) == {
            "title_ja": "題",
            "comment_highlights": [],
        }

    @pytest.mark.parametrize(
        "data",
        [
            {"comment_highlights": []},
            {"title_ja": "題"},
            {},
            {"title_ja": "題", "comment_highlights": "ではない"},
            {"title_ja": "題", "comment_highlights": ["文字列"]},
            {"title_ja": ["題"], "comment_highlights": []},
        ],
    )
    def test_missing_or_broken_required_key_raises(self, data):
        """必須キーの欠落と型違いは検証エラーになる."""
        with pytest.raises(ValidationError):
            DetectiveAnalysis.model_validate(data)

    def test_extra_keys_are_kept(self):
        """未知のキーは捨てない（入れ子も）."""
        dumped = _dump(
            DetectiveAnalysis,
            title_ja="題",
            comment_highlights=[{"author": "a", "extra_inner": 1}],
            extra_outer={"k": "v"},
        )

        assert dumped["extra_outer"] == {"k": "v"}
        assert dumped["comment_highlights"] == [{"author": "a", "extra_inner": 1}]

    def test_null_strings_become_defaults(self):
        """文字列項目の null は既定値に寄せる."""
        dumped = _dump(
            DetectiveAnalysis,
            title_ja=None,
            why_trending=None,
            background=None,
            summary=None,
            comment_highlights=[{"author": None, "quote": None, "stance": None}],
        )

        assert dumped["title_ja"] == ""
        assert dumped["why_trending"] == ""
        assert dumped["background"] == ""
        assert dumped["summary"] == ""
        assert dumped["comment_highlights"] == [
            {"author": "Anonymous", "quote": "", "stance": ""}
        ]

    def test_null_required_list_becomes_empty(self):
        """必須のリストが null でもキーがあれば通す（従来の検査と同じ）."""
        dumped = _dump(DetectiveAnalysis, title_ja="題", comment_highlights=None)

        assert dumped["comment_highlights"] == []

    def test_numbers_in_text_fields_become_strings(self):
        """文字列項目の数値は文字列にする."""
        dumped = _dump(DetectiveAnalysis, title_ja=2026, comment_highlights=[])

        assert dumped["title_ja"] == "2026"

    @pytest.mark.parametrize(
        "data",
        [
            {"title_ja": "題", "comment_highlights": [{"author": "a"}]},
            {
                "title_ja": None,
                "why_trending": None,
                "background": None,
                "summary": None,
                "comment_highlights": [{"author": None, "quote": None, "stance": None}],
            },
        ],
    )
    def test_reporter_accepts_omitted_and_null_values(self, data):
        """省略や null を含む応答でも Slack ブロックを組み立てられる."""
        blocks = _reporter()._build_detective_blocks(
            HN_URL, "", THREAD_RESULT, _dump(DetectiveAnalysis, **data)
        )

        assert blocks


@pytest.mark.unit
class TestDevilsAdvocateAnalysis:
    """DevilsAdvocateAnalysis のテスト."""

    def test_required_keys_only_is_valid_and_adds_no_keys(self):
        """必須キーだけで通り、LLM が返していないキーを足さない."""
        assert _dump(DevilsAdvocateAnalysis, concerns=[], critical_comments=[]) == {
            "concerns": [],
            "critical_comments": [],
        }

    @pytest.mark.parametrize(
        "data",
        [
            {"critical_comments": []},
            {"concerns": []},
            {"concerns": "ではない", "critical_comments": []},
            {"concerns": [None], "critical_comments": []},
            {"concerns": [], "critical_comments": ["文字列"]},
            {"concerns": [], "critical_comments": [], "past_cases": ["文字列"]},
        ],
    )
    def test_missing_or_broken_key_raises(self, data):
        """必須キーの欠落と型違いは検証エラーになる."""
        with pytest.raises(ValidationError):
            DevilsAdvocateAnalysis.model_validate(data)

    def test_null_values_become_defaults(self):
        """リストと文字列項目の null は既定値に寄せる."""
        dumped = _dump(
            DevilsAdvocateAnalysis,
            concerns=None,
            past_cases=[{"name": None, "lesson": None}],
            critical_comments=[{"author": None, "quote": None, "angle": None}],
            summary=None,
        )

        assert dumped == {
            "concerns": [],
            "past_cases": [{"name": "", "lesson": ""}],
            "critical_comments": [{"author": "Anonymous", "quote": "", "angle": ""}],
            "summary": "",
        }

    @pytest.mark.parametrize(
        "data",
        [
            {"concerns": ["懸念"], "critical_comments": [{"quote": "q"}]},
            {
                "concerns": None,
                "past_cases": [{"name": None, "lesson": None}],
                "critical_comments": [{"author": None, "quote": None, "angle": None}],
                "summary": None,
            },
        ],
    )
    def test_reporter_accepts_omitted_and_null_values(self, data):
        """省略や null を含む応答でも Slack ブロックを組み立てられる."""
        blocks = _reporter()._build_devils_advocate_blocks(
            HN_URL, "", THREAD_RESULT, _dump(DevilsAdvocateAnalysis, **data)
        )

        assert blocks


@pytest.mark.unit
class TestSecurityAnalysis:
    """SecurityAnalysis のテスト."""

    def test_required_keys_only_is_valid_and_adds_no_keys(self):
        """必須キーだけで通り、LLM が返していないキーを足さない."""
        assert _dump(SecurityAnalysis, severity="high", summary="対応") == {
            "severity": "high",
            "summary": "対応",
        }

    @pytest.mark.parametrize(
        "data",
        [
            {"summary": "対応"},
            {"severity": "high"},
            {"severity": "high", "summary": "対応", "cve_ids": "CVE-1"},
            {"severity": "high", "summary": "対応", "official_patch": "なし"},
        ],
    )
    def test_missing_or_broken_key_raises(self, data):
        """必須キーの欠落と型違いは検証エラーになる."""
        with pytest.raises(ValidationError):
            SecurityAnalysis.model_validate(data)

    def test_null_values_from_prompt_rule_are_accepted(self):
        """プロンプトが許す null（情報なし）を受け入れて既定値に寄せる."""
        dumped = _dump(
            SecurityAnalysis,
            severity=None,
            summary=None,
            cve_ids=None,
            affected=None,
            workarounds=None,
            official_patch=None,
        )

        assert dumped == {
            "severity": "unknown",
            "summary": "",
            "cve_ids": [],
            "affected": [],
            "workarounds": [],
            "official_patch": None,
        }

    @pytest.mark.parametrize(
        "patch",
        [
            {"available": True, "version": "1.6.0 以降", "url": "https://example.com"},
            {"available": False, "version": None, "url": None},
            {"available": None},
            {"available": "unknown", "version": ["1.2", "2.0"]},
            {"available": True, "version": 1.2},
        ],
    )
    def test_official_patch_is_kept_as_returned(self, patch):
        """公式パッチの available と version は Reporter が扱える値をそのまま残す."""
        dumped = _dump(
            SecurityAnalysis, severity="high", summary="対応", official_patch=patch
        )

        assert dumped["official_patch"] == patch

    @pytest.mark.parametrize(
        "data",
        [
            {"severity": "high", "summary": "対応"},
            {
                "severity": None,
                "summary": None,
                "cve_ids": None,
                "affected": None,
                "workarounds": None,
                "official_patch": {"available": None},
            },
            {
                "severity": "high",
                "summary": "対応",
                "official_patch": {"available": "unknown", "version": ["1.2"]},
            },
        ],
    )
    def test_reporter_accepts_omitted_and_null_values(self, data):
        """省略や null を含む応答でも Slack ブロックを組み立てられる."""
        blocks = _reporter()._build_security_responder_blocks(
            HN_URL, "", THREAD_RESULT, _dump(SecurityAnalysis, **data)
        )

        assert blocks
