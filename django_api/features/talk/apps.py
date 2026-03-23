"""Talk application configuration."""

from django.apps import AppConfig


class TalkAppConfig(AppConfig):
    """会話生成アプリ設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "features.talk"
    label = "talk"
    verbose_name = "会話生成"
