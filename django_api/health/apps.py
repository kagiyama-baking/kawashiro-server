"""ヘルスチェックアプリ設定"""

from django.apps import AppConfig


class HealthConfig(AppConfig):
    """ヘルスチェックアプリケーション設定"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "health"
    verbose_name = "ヘルスチェック"
