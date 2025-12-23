from django.apps import AppConfig


class MsGraphConfig(AppConfig):
    """Microsoft Graph API共通設定アプリケーションの設定クラス"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "ms_graph"
    verbose_name = "Microsoft Graph API設定"
