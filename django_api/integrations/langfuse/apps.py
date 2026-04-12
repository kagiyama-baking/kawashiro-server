"""Langfuse統合アプリ設定"""

from django.apps import AppConfig


class LangfuseConfig(AppConfig):
    """Langfuse統合アプリケーション設定"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.langfuse"
    label = "langfuse_integration"
    verbose_name = "Langfuse"
