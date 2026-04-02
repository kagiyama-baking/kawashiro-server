"""Slack連携アプリ設定."""

from django.apps import AppConfig


class SlackConfig(AppConfig):
    """Slack通知連携アプリ設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.slack"
    label = "slack"
