"""設定取得ヘルパー"""

from dataclasses import dataclass

from .exceptions import ConfigurationError


@dataclass
class MSGraphSettings:
    """Microsoft Graph API設定を保持するデータクラス"""

    tenant_id: str
    client_id: str
    cert_thumbprint: str
    private_key: str
    target_user: str


def get_ms_graph_settings() -> MSGraphSettings:
    """
    データベースから有効なMicrosoft Graph API設定を取得する

    Returns:
        MSGraphSettings: 設定データクラス

    Raises:
        ConfigurationError: 有効な設定が存在しないか、必須フィールドが空の場合
    """
    from .models import MSGraphConfig

    try:
        config = MSGraphConfig.objects.get_active_config()
    except MSGraphConfig.DoesNotExist as err:
        raise ConfigurationError(
            "有効なMicrosoft Graph API設定がありません。\n"
            "Django管理画面から設定を作成し、有効にしてください。"
        ) from err

    # 必須フィールドのバリデーション
    missing_fields = []
    if not config.tenant_id:
        missing_fields.append("テナントID")
    if not config.client_id:
        missing_fields.append("クライアントID")
    if not config.cert_thumbprint:
        missing_fields.append("証明書サムプリント")
    if not config.private_key:
        missing_fields.append("秘密鍵")
    if not config.target_user:
        missing_fields.append("対象ユーザー")

    if missing_fields:
        raise ConfigurationError(
            f"設定「{config.name}」の以下の項目が未入力です: {', '.join(missing_fields)}\n"
            "Django管理画面から設定を行ってください。"
        )

    return MSGraphSettings(
        tenant_id=config.tenant_id,
        client_id=config.client_id,
        cert_thumbprint=config.cert_thumbprint,
        private_key=config.private_key,
        target_user=config.target_user,
    )
