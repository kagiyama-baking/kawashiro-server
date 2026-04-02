"""Reporter — 調査結果をSlackに通知."""

import logging

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
                f"• <{s['url']}|{_escape_mrkdwn(s['title'])}>" for s in sources
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
                        + (f"\n<{thread_url}|:link: 元記事>" if thread_url else "")
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
                        + (f"\n<{thread_url}|:link: 元記事>" if thread_url else "")
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

    def report_memory(self, result: dict) -> bool:
        """Memory調査結果をSlackに通知."""
        if not result.get("has_similar"):
            return False

        client = self.slack_client
        if client is None:
            return False

        hn_url = HN_ITEM_URL.format(hn_id=result["thread_hn_id"])

        similar_lines = []
        for st in result.get("similar_threads", []):
            st_url = HN_ITEM_URL.format(hn_id=st["hn_id"])
            safe_title = _escape_mrkdwn(st["title"])
            similar_lines.append(
                f"• <{st_url}|{safe_title}> (類似度: {st['similarity']:.0%})"
            )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": ":brain: HN Memory Report"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{hn_url}|{_escape_mrkdwn(result['thread_title'])}>* に類似する過去スレッド:\n"
                        + "\n".join(similar_lines)
                    ),
                },
            },
        ]

        try:
            client.send_blocks(
                blocks=blocks,
                text=f"HN Memory: {result['thread_title']} に類似スレッド発見",
            )
            logger.info("Memory結果をSlackに送信: [%d]", result["thread_hn_id"])
            return True
        except SlackError:
            logger.exception("Slack送信に失敗: [%d]", result["thread_hn_id"])
            return False

    def report_hypothesis(self, result: dict) -> bool:
        """Hypothesis調査結果をSlackに通知."""
        if not result.get("has_claims"):
            return False

        client = self.slack_client
        if client is None:
            return False

        hn_url = HN_ITEM_URL.format(hn_id=result["thread_hn_id"])

        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":scales: HN Hypothesis Report",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{hn_url}|{_escape_mrkdwn(result['thread_title'])}>*\n"
                        f"{result['claims_found']}件の対立主張を検証"
                    ),
                },
            },
        ]

        for verdict in result.get("verdicts", []):
            topic = _escape_mrkdwn(verdict.get("topic", ""))
            claim_a = _escape_mrkdwn(verdict.get("claim_a", ""))
            claim_b = _escape_mrkdwn(verdict.get("claim_b", ""))
            verdict_text = _escape_mrkdwn(verdict.get("verdict", ""))

            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*{topic}*\n"
                            f":a: {claim_a}\n"
                            f":b: {claim_b}\n\n"
                            f"{_truncate(verdict_text, 2000)}"
                        ),
                    },
                }
            )

        try:
            client.send_blocks(
                blocks=blocks,
                text=f"HN Hypothesis: {result['thread_title']}",
            )
            logger.info("Hypothesis結果をSlackに送信: [%d]", result["thread_hn_id"])
            return True
        except SlackError:
            logger.exception("Slack送信に失敗: [%d]", result["thread_hn_id"])
            return False


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
