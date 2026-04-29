"""Slack通知クライアントのテスト."""

from unittest.mock import Mock, patch

import pytest

from integrations.slack.client import SlackClient
from integrations.slack.config import SlackSettings
from integrations.slack.exceptions import SlackConfigurationError, SlackSendError

pytestmark = pytest.mark.django_db


@pytest.fixture
def mock_slack_settings():
    """Slack DB設定のモック."""
    settings = SlackSettings(webhook_url="https://hooks.slack.com/test-db")
    with patch(
        "integrations.slack.client.get_slack_settings",
        return_value=settings,
    ):
        yield settings


@pytest.mark.unit
class TestSlackClient:
    """SlackClientのテスト."""

    def test_init_without_db_config_raises_error(self):
        """DB設定なしで初期化するとエラーになる."""
        with pytest.raises(SlackConfigurationError):
            SlackClient()

    def test_init_with_explicit_webhook_url(self, mock_slack_settings):
        """明示的にWebhook URLを指定して初期化できる."""
        client = SlackClient(webhook_url="https://hooks.slack.com/explicit")
        assert client.webhook_url == "https://hooks.slack.com/explicit"

    def test_init_falls_back_to_db_settings(self, mock_slack_settings):
        """引数省略時はDB設定から取得する."""
        client = SlackClient()
        assert client.webhook_url == "https://hooks.slack.com/test-db"

    @patch("integrations.slack.client.WebhookClient")
    def test_send_message_success(self, mock_webhook_class, mock_slack_settings):
        """メッセージ送信に成功する."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.body = "ok"
        mock_webhook_class.return_value.send.return_value = mock_response

        client = SlackClient(webhook_url="https://hooks.slack.com/test")
        response = client.send_message("テストメッセージ")

        assert response.status_code == 200
        mock_webhook_class.return_value.send.assert_called_once_with(
            text="テストメッセージ"
        )

    @patch("integrations.slack.client.WebhookClient")
    def test_send_message_failure_raises_error(
        self, mock_webhook_class, mock_slack_settings
    ):
        """メッセージ送信失敗時にSlackSendErrorを送出する."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.body = "invalid_token"
        mock_webhook_class.return_value.send.return_value = mock_response

        client = SlackClient(webhook_url="https://hooks.slack.com/test")

        with pytest.raises(SlackSendError, match="Slack送信失敗"):
            client.send_message("テスト")

    @patch("integrations.slack.client.WebhookClient")
    def test_send_blocks_success(self, mock_webhook_class, mock_slack_settings):
        """Block Kit形式メッセージの送信に成功する."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_webhook_class.return_value.send.return_value = mock_response

        client = SlackClient(webhook_url="https://hooks.slack.com/test")
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}]
        response = client.send_blocks(blocks=blocks, text="fallback")

        assert response.status_code == 200
        mock_webhook_class.return_value.send.assert_called_once_with(
            text="fallback", blocks=blocks
        )
