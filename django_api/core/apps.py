from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Coreアプリケーションの設定クラス"""

    # データベースの主キーフィールドのデフォルト設定（64ビット整数）
    default_auto_field = "django.db.models.BigAutoField"
    # アプリケーション名
    name = "core"

    def ready(self):
        """アプリケーション起動時にトレーシングを初期化."""
        from core.tracing import setup_tracing

        setup_tracing()
