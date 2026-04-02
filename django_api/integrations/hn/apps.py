"""HN連携アプリ設定."""

from django.apps import AppConfig


class HNConfig(AppConfig):
    """Hacker News連携アプリ設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.hn"
    label = "hn"
