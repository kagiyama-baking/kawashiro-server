"""Microsoft Graph API統合アプリ設定"""

from django.apps import AppConfig


class MsgraphConfig(AppConfig):
    """Microsoft Graph API統合アプリケーション設定"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.msgraph"
    label = "msgraph_config"
    verbose_name = "Microsoft 365"
