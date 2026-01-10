from django.apps import AppConfig


class MsgraphConfigConfig(AppConfig):
    """Microsoft Graph API共通設定アプリケーションの設定クラス"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "msgraph_config"
    verbose_name = "Microsoft Graph API設定"
