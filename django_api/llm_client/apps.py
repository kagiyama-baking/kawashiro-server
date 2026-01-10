"""Djangoアプリ設定."""

from django.apps import AppConfig


class LlmClientConfig(AppConfig):
    """LLMクライアントアプリの設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "llm_client"
    verbose_name = "LLMクライアント"
