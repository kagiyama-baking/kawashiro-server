"""LLM設定アプリ"""

from django.apps import AppConfig


class LlmConfigConfig(AppConfig):
    """LLM設定アプリケーション設定"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "llm_config"
    verbose_name = "LLM設定"
