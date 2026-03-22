"""Generate application configuration."""

from django.apps import AppConfig


class GenerateAppConfig(AppConfig):
    """テキスト生成アプリ設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "features.generate"
    label = "generate"
    verbose_name = "テキスト生成"
