"""Tavily連携アプリ設定."""

from django.apps import AppConfig


class TavilyConfig(AppConfig):
    """Tavily Web検索連携アプリ設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.tavily"
    label = "tavily"
