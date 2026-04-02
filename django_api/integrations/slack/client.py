"""Slack Incoming Webhookクライアント."""

import logging

from slack_sdk.webhook import WebhookClient, WebhookResponse

from .config import get_slack_settings
from .exceptions import SlackSendError

logger = logging.getLogger(__name__)


class SlackClient:
    """Slack Incoming Webhookクライアント."""

    def __init__(self, webhook_url: str | None = None):
        """クライアントを初期化.

        設定の優先順位:
        1. 引数で明示的に指定された値
        2. データベースの有効な設定

        Args:
            webhook_url: Slack Webhook URL。省略時はDB設定から取得

        Raises:
            SlackConfigurationError: DB設定がない、またはWebhook URLが未設定の場合
        """
        db_settings = get_slack_settings()
        self.webhook_url = webhook_url or db_settings.webhook_url
        self._client = WebhookClient(self.webhook_url)

    def send_message(self, text: str) -> WebhookResponse:
        """テキストメッセージを送信.

        Args:
            text: 送信するメッセージ

        Returns:
            WebhookResponse

        Raises:
            SlackSendError: 送信失敗時
        """
        try:
            response = self._client.send(text=text)
            if response.status_code != 200:
                raise SlackSendError(
                    f"Slack送信失敗: status={response.status_code}, body={response.body}"
                )
            logger.info("Slackメッセージ送信完了")
            return response
        except SlackSendError:
            raise
        except Exception as e:
            raise SlackSendError(f"Slack送信中にエラーが発生しました: {e}") from e

    def send_blocks(self, blocks: list[dict], text: str = "") -> WebhookResponse:
        """Block Kit形式のメッセージを送信.

        Args:
            blocks: Block Kit形式のブロックリスト
            text: フォールバックテキスト

        Returns:
            WebhookResponse

        Raises:
            SlackSendError: 送信失敗時
        """
        try:
            response = self._client.send(text=text, blocks=blocks)
            if response.status_code != 200:
                raise SlackSendError(
                    f"Slack送信失敗: status={response.status_code}, body={response.body}"
                )
            logger.info("Slackブロックメッセージ送信完了")
            return response
        except SlackSendError:
            raise
        except Exception as e:
            raise SlackSendError(f"Slack送信中にエラーが発生しました: {e}") from e
