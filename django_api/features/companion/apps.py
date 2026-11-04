"""Companion アプリ設定."""

from django.apps import AppConfig


class CompanionAppConfig(AppConfig):
    """Companion エージェントのアプリ設定.

    モデル `CompanionConfig` と名前が重ならないよう `AppConfig` を付ける（Talk と同じ）。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "features.companion"
    label = "companion"
    verbose_name = "Companion"
