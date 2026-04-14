"""Reporter — 調査結果をSlackに通知."""

import logging
from urllib.parse import urlparse

from integrations.slack.client import SlackClient
from integrations.slack.exceptions import SlackError

logger = logging.getLogger(__name__)

HN_ITEM_URL = "https://news.ycombinator.com/item?id={hn_id}"

# Slackブロックのテキスト上限
MAX_SECTION_TEXT = 3000


class Reporter:
    """調査結果をSlackに通知するレポーター."""

    def __init__(self, slack_client: SlackClient | None = None):
        """初期化."""
        self._slack_client = slack_client

    @property
    def slack_client(self) -> SlackClient | None:
        """Slackクライアントを取得（未設定時はNone）."""
        if self._slack_client is None:
            try:
                self._slack_client = SlackClient()
            except SlackError:
                logger.warning("Slack Webhook URLが未設定のため通知をスキップ")
                return None
        return self._slack_client

    def report_detective(self, result: dict) -> bool:
        """Detective調査結果をSlackに通知.

        Args:
            result: Detective Agentの調査結果

        Returns:
            送信成功ならTrue
        """
        client = self.slack_client
        if client is None:
            return False

        hn_url = HN_ITEM_URL.format(hn_id=result["thread_hn_id"])
        thread_url = result.get("thread_url", "")
        analysis = result.get("analysis", {})

        # JSON構造化レスポンスの場合
        if isinstance(analysis, dict):
            blocks = self._build_detective_blocks(hn_url, thread_url, result, analysis)
        else:
            # フォールバック: プレーンテキスト
            blocks = self._build_detective_fallback_blocks(
                hn_url, thread_url, result, str(analysis)
            )

        sources = result.get("background_sources", [])
        if sources:
            source_text = "\n".join(
                f"• <{safe_url}|{_escape_mrkdwn(s['title'])}>"
                for s in sources
                if (safe_url := _sanitize_url(s.get("url")))
            )
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f":books: 参考情報:\n{source_text}"}
                    ],
                }
            )

        try:
            client.send_blocks(
                blocks=blocks,
                text=f"HN Detective: {result['thread_title']}",
            )
            logger.info("Detective結果をSlackに送信: [%d]", result["thread_hn_id"])
            return True
        except SlackError:
            logger.exception("Slack送信に失敗: [%d]", result["thread_hn_id"])
            return False

    def _build_detective_blocks(
        self,
        hn_url: str,
        thread_url: str,
        result: dict,
        analysis: dict,
    ) -> list[dict]:
        """構造化JSON分析からSlackブロックを構築."""
        safe_title = _escape_mrkdwn(result["thread_title"])
        title_ja = analysis.get("title_ja", "")

        # ヘッダー
        header_text = f":mag: {safe_title}"
        if title_ja:
            header_text = f":mag: {_escape_mrkdwn(title_ja)}"

        blocks: list[dict] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": _truncate(header_text, 150)},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{hn_url}|{safe_title}>*"
                        + (
                            f"\n<{_sanitize_url(thread_url)}|:link: 元記事>"
                            if _sanitize_url(thread_url)
                            else ""
                        )
                        + f"\n{result.get('score_info', '')}"
                    ),
                },
            },
        ]

        # なぜ注目されているか
        why = analysis.get("why_trending", "")
        if why:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*:fire: なぜ注目されているか*\n{_escape_mrkdwn(why)}",
                    },
                }
            )

        # 背景情報
        bg = analysis.get("background", "")
        if bg:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*:bulb: 背景情報*\n{_escape_mrkdwn(bg)}",
                    },
                }
            )

        # コメントハイライト（5chまとめ風）
        highlights = analysis.get("comment_highlights", [])
        if highlights:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*:speech_balloon: コメントピックアップ（{len(highlights)}件）*",
                    },
                }
            )

            # コメントを2-3件ずつブロックにまとめる（Slack制限対策）
            comment_lines: list[str] = []
            for h in highlights:
                author = _escape_mrkdwn(h.get("author", "Anonymous"))
                quote = _escape_mrkdwn(h.get("quote", ""))
                stance = h.get("stance", "")
                stance_emoji = _stance_to_emoji(stance)

                comment_lines.append(f"{stance_emoji} *{author}*\n> {quote}")

            # 3件ずつまとめてsectionブロックに
            chunk_size = 3
            for i in range(0, len(comment_lines), chunk_size):
                chunk = comment_lines[i : i + chunk_size]
                text = "\n\n".join(chunk)
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": _truncate(text, MAX_SECTION_TEXT),
                        },
                    }
                )

        # 総括
        summary = analysis.get("summary", "")
        if summary:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*:memo: 総括*\n{_escape_mrkdwn(summary)}",
                    },
                }
            )

        return blocks

    def report_devils_advocate(self, result: dict) -> bool:
        """Devil's Advocate 分析結果をSlackに通知.

        Args:
            result: Devil's Advocate Agent の分析結果

        Returns:
            送信成功ならTrue
        """
        client = self.slack_client
        if client is None:
            return False

        hn_url = HN_ITEM_URL.format(hn_id=result["thread_hn_id"])
        thread_url = result.get("thread_url", "")
        analysis = result.get("analysis", {})

        blocks = self._build_devils_advocate_blocks(
            hn_url, thread_url, result, analysis
        )

        try:
            client.send_blocks(
                blocks=blocks,
                text=f"HN Devil's Advocate: {result['thread_title']}",
            )
            logger.info(
                "Devil's Advocate 結果をSlackに送信: [%d]", result["thread_hn_id"]
            )
            return True
        except SlackError:
            logger.exception("Slack送信に失敗: [%d]", result["thread_hn_id"])
            return False

    def report_security_responder(self, result: dict) -> bool:
        """Security Responder 分析結果をSlackに通知.

        Args:
            result: Security Responder Agent の分析結果

        Returns:
            送信成功ならTrue
        """
        client = self.slack_client
        if client is None:
            return False

        hn_url = HN_ITEM_URL.format(hn_id=result["thread_hn_id"])
        thread_url = result.get("thread_url", "")
        analysis = result.get("analysis", {})

        blocks = self._build_security_responder_blocks(
            hn_url, thread_url, result, analysis
        )

        sources = result.get("search_sources", [])
        if sources:
            source_text = "\n".join(
                f"• <{safe_url}|{_escape_mrkdwn(s['title'])}>"
                for s in sources
                if (safe_url := _sanitize_url(s.get("url")))
            )
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f":books: 関連情報:\n{source_text}",
                        }
                    ],
                }
            )

        try:
            client.send_blocks(
                blocks=blocks,
                text=f"HN Security: {result['thread_title']}",
            )
            logger.info(
                "Security Responder 結果をSlackに送信: [%d]", result["thread_hn_id"]
            )
            return True
        except SlackError:
            logger.exception("Slack送信に失敗: [%d]", result["thread_hn_id"])
            return False

    def _build_devils_advocate_blocks(
        self,
        hn_url: str,
        thread_url: str,
        result: dict,
        analysis: dict,
    ) -> list[dict]:
        """Devil's Advocate Slack ブロックを構築."""
        safe_title = _escape_mrkdwn(result["thread_title"])

        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": _truncate(":no_entry: HN民の辛口な意見", 150),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{hn_url}|{safe_title}>*"
                        + (
                            f"\n<{_sanitize_url(thread_url)}|:link: 元記事>"
                            if _sanitize_url(thread_url)
                            else ""
                        )
                        + f"\n{result.get('score_info', '')}"
                    ),
                },
            },
        ]

        concerns = analysis.get("concerns", [])
        if concerns:
            bullet = "\n".join(f"• {_escape_mrkdwn(c)}" for c in concerns)
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": _truncate(
                            f"*:warning: 懸念点・トレードオフ*\n{bullet}",
                            MAX_SECTION_TEXT,
                        ),
                    },
                }
            )

        past_cases = analysis.get("past_cases", [])
        if past_cases:
            bullet = "\n".join(
                f"• *{_escape_mrkdwn(pc.get('name', ''))}*: "
                f"{_escape_mrkdwn(pc.get('lesson', ''))}"
                for pc in past_cases
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": _truncate(
                            f"*:alarm_clock: 過去の類似事例*\n{bullet}",
                            MAX_SECTION_TEXT,
                        ),
                    },
                }
            )

        critical_comments = analysis.get("critical_comments", [])
        if critical_comments:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*:speaking_head_in_silhouette: 辛口コメント"
                            f"（{len(critical_comments)}件）*"
                        ),
                    },
                }
            )
            lines = []
            for cc in critical_comments:
                author = _escape_mrkdwn(cc.get("author", "Anonymous"))
                quote = _escape_mrkdwn(cc.get("quote", ""))
                angle = _escape_mrkdwn(cc.get("angle", ""))
                angle_suffix = f" _({angle})_" if angle else ""
                lines.append(f":no_entry_sign: *{author}*{angle_suffix}\n> {quote}")

            chunk_size = 3
            for i in range(0, len(lines), chunk_size):
                chunk = lines[i : i + chunk_size]
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": _truncate("\n\n".join(chunk), MAX_SECTION_TEXT),
                        },
                    }
                )

        summary = analysis.get("summary", "")
        if summary:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*:memo: 総括*\n{_escape_mrkdwn(summary)}",
                    },
                }
            )

        return blocks

    def _build_security_responder_blocks(
        self,
        hn_url: str,
        thread_url: str,
        result: dict,
        analysis: dict,
    ) -> list[dict]:
        """Security Responder Slack ブロックを構築."""
        safe_title = _escape_mrkdwn(result["thread_title"])
        severity = (analysis.get("severity") or "unknown").lower()

        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": _truncate(
                        ":rotating_light: セキュリティインシデント詳細", 150
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{hn_url}|{safe_title}>*"
                        + (
                            f"\n<{_sanitize_url(thread_url)}|:link: 元記事>"
                            if _sanitize_url(thread_url)
                            else ""
                        )
                        + f"\n{result.get('score_info', '')}"
                        + f"\n{_severity_emoji(severity)} *Severity:* `{severity}`"
                    ),
                },
            },
        ]

        cve_ids = analysis.get("cve_ids") or []
        cve_text = (
            ", ".join(f"`{_escape_mrkdwn(c)}`" for c in cve_ids)
            if cve_ids
            else "未特定"
        )
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*:label: CVE*\n{cve_text}",
                },
            }
        )

        affected = analysis.get("affected") or []
        if affected:
            bullet = "\n".join(f"• {_escape_mrkdwn(a)}" for a in affected)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": _truncate(
                            f"*:dart: 影響範囲*\n{bullet}", MAX_SECTION_TEXT
                        ),
                    },
                }
            )

        workarounds = analysis.get("workarounds") or []
        if workarounds:
            bullet = "\n".join(f"• {_escape_mrkdwn(w)}" for w in workarounds)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": _truncate(
                            f"*:shield: 回避策*\n{bullet}", MAX_SECTION_TEXT
                        ),
                    },
                }
            )

        patch = analysis.get("official_patch") or {}
        patch_text = _format_official_patch(patch)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*:wrench: 公式パッチ*\n{patch_text}",
                },
            }
        )

        summary = analysis.get("summary", "")
        if summary:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*:memo: 対応指針*\n{_escape_mrkdwn(summary)}",
                    },
                }
            )

        return blocks

    def _build_detective_fallback_blocks(
        self,
        hn_url: str,
        thread_url: str,
        result: dict,
        analysis_text: str,
    ) -> list[dict]:
        """プレーンテキスト分析のフォールバックブロック."""
        safe_title = _escape_mrkdwn(result["thread_title"])

        return [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": ":mag: HN Detective Report"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{hn_url}|{safe_title}>*\n"
                        f"{result.get('score_info', '')}"
                        + (
                            f"\n<{_sanitize_url(thread_url)}|:link: 元記事>"
                            if _sanitize_url(thread_url)
                            else ""
                        )
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _truncate(analysis_text, MAX_SECTION_TEXT),
                },
            },
        ]


def _truncate(text: str, max_length: int) -> str:
    """テキストを最大長で切り詰める."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _escape_mrkdwn(text: str) -> str:
    """Slack mrkdwn特殊文字をエスケープ."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _stance_to_emoji(stance: str) -> str:
    """コメントの立場をemojiに変換."""
    mapping = {
        "肯定": ":white_check_mark:",
        "批判": ":no_entry_sign:",
        "技術的指摘": ":wrench:",
        "補足": ":heavy_plus_sign:",
        "ユーモア": ":laughing:",
    }
    return mapping.get(stance, ":speech_balloon:")


def _severity_emoji(severity: str) -> str:
    """severity 値を色付き emoji に変換."""
    mapping = {
        "critical": ":red_circle:",
        "high": ":large_orange_circle:",
        "medium": ":large_yellow_circle:",
        "low": ":large_blue_circle:",
        "unknown": ":white_circle:",
    }
    return mapping.get(severity, ":white_circle:")


def _format_official_patch(patch: dict) -> str:
    """公式パッチ情報を Slack mrkdwn に整形."""
    if not patch or not patch.get("available"):
        return "未リリース（回避策の適用を推奨）"
    version = patch.get("version")
    url = _sanitize_url(patch.get("url"))
    parts = ["リリース済"]
    if version:
        parts.append(f"バージョン: `{_escape_mrkdwn(str(version))}`")
    if url:
        parts.append(f"<{url}|:link: 公式情報>")
    return "\n".join(parts)


def _sanitize_url(url: str | None) -> str | None:
    """LLM 生成 URL を検証（http/https のみ、mrkdwn 制御文字を含まない）.

    Slack の mrkdwn リンク `<URL|text>` は `|`, `<`, `>`, 改行が含まれると
    構造が崩れて意図しないテキストがリンクラベルとして表示されるため、
    これらを含む URL は拒否する。また `javascript:` 等の危険スキームも拒否。
    """
    if not url:
        return None
    if any(ch in url for ch in ("|", "<", ">", "\n", "\r")):
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    return url
