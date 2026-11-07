"""Talk application configuration."""

from django.apps import AppConfig


class TalkAppConfig(AppConfig):
    """Talk（チャット）アプリ設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "features.talk"
    label = "talk"
    verbose_name = "Talk"

    def ready(self) -> None:
        from . import signals  # noqa: F401
