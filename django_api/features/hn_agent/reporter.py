"""Reporter — 調査結果をSlackに通知."""

import logging

from integrations.slack.client import SlackClient
from integrations.slack.exceptions import SlackError

logger = logging.getLogger(__name__)

HN_ITEM_URL = "https://news.ycombinator.com/item?id={hn_id}"


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

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔍 HN Detective Report",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{hn_url}|{_escape_mrkdwn(result['thread_title'])}>*\n"
                        f"{result.get('score_info', '')}"
                        + (f"\n<{thread_url}|元記事>" if thread_url else "")
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _truncate(result.get("analysis", ""), 2900),
                },
            },
        ]

        sources = result.get("background_sources", [])
        if sources:
            source_text = "\n".join(f"• <{s['url']}|{s['title']}>" for s in sources)
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"📚 参考情報:\n{source_text}",
                        }
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

    def report_memory(self, result: dict) -> bool:
        """Memory調査結果をSlackに通知.

        Args:
            result: Memory Agentの調査結果

        Returns:
            送信成功ならTrue
        """
        if not result.get("has_similar"):
            return False

        client = self.slack_client
        if client is None:
            return False

        hn_url = HN_ITEM_URL.format(hn_id=result["thread_hn_id"])

        similar_lines = []
        for st in result.get("similar_threads", []):
            st_url = HN_ITEM_URL.format(hn_id=st["hn_id"])
            similar_lines.append(
                f"• <{st_url}|{st['title']}> (類似度: {st['similarity']:.0%})"
            )

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🧠 HN Memory Report",
                },
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
        """Hypothesis調査結果をSlackに通知.

        Args:
            result: Hypothesis Agentの調査結果

        Returns:
            送信成功ならTrue
        """
        if not result.get("has_claims"):
            return False

        client = self.slack_client
        if client is None:
            return False

        hn_url = HN_ITEM_URL.format(hn_id=result["thread_hn_id"])

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚖️ HN Hypothesis Report",
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
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*{verdict['topic']}*\n"
                            f"A: {verdict['claim_a']}\n"
                            f"B: {verdict['claim_b']}\n\n"
                            f"{_truncate(verdict['verdict'], 2000)}"
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
