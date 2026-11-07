"""Talk application configuration."""

from django.apps import AppConfig


class TalkAppConfig(AppConfig):
    """Talk（チャット）アプリ設定.

    旧 Talk Generator（会話生成設定と /talk/synthesize/）は削除まで同じアプリに残る。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "features.talk"
    label = "talk"
    verbose_name = "Talk"

    def ready(self) -> None:
        from . import signals  # noqa: F401
