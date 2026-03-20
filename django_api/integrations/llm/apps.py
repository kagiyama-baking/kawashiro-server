"""LLM統合アプリ設定"""

from django.apps import AppConfig


class LlmConfig(AppConfig):
    """LLM統合アプリケーション設定"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.llm"
    label = "llm_config"
    verbose_name = "LLM設定"
