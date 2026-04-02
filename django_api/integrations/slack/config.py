"""Slack設定取得ヘルパー."""

from dataclasses import dataclass

from .exceptions import SlackConfigurationError


@dataclass
class SlackSettings:
    """Slack通知設定を保持するデータクラス."""

    webhook_url: str


def get_slack_settings() -> SlackSettings:
    """データベースから有効なSlack通知設定を取得.

    Returns:
        SlackSettings: 設定データクラス

    Raises:
        SlackConfigurationError: 有効な設定が存在しないか、Webhook URLが空の場合
    """
    from .models import SlackConfig

    try:
        config = SlackConfig.objects.get_active_config()
    except SlackConfig.DoesNotExist as err:
        raise SlackConfigurationError(
            "有効なSlack通知設定がありません。\n"
            "Django管理画面から設定を作成し、有効にしてください。"
        ) from err

    if not config.webhook_url:
        raise SlackConfigurationError(
            f"設定「{config.name}」のWebhook URLが未入力です。\n"
            "Django管理画面から設定を行ってください。"
        )

    return SlackSettings(webhook_url=config.webhook_url)
