"""Djangoアプリ設定."""

from django.apps import AppConfig


class AssistantConfig(AppConfig):
    """Assistantアプリの設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "assistant"
    verbose_name = "AIアシスタント"
