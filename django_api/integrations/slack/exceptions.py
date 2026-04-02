"""Slack通知例外定義."""


class SlackError(Exception):
    """Slack関連エラーの基底クラス."""


class SlackConfigurationError(SlackError):
    """Webhook URL未設定エラー."""


class SlackSendError(SlackError):
    """メッセージ送信エラー."""
