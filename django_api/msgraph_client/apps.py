"""msgraph_client アプリケーション設定"""

from django.apps import AppConfig


class MsgraphClientConfig(AppConfig):
    """Microsoft Graph API クライアントのアプリケーション設定"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "msgraph_client"
    verbose_name = "Microsoft Graph API クライアント"
