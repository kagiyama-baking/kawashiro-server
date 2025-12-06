"""OneDrive設定モデル"""

from django.db import models

from .encryption import decrypt_value, encrypt_value


class MSGraphConfigManager(models.Manager):
    """MSGraphConfigのカスタムマネージャー"""

    def get_config(self):
        """
        設定を取得する（シングルトン）

        Returns:
            MSGraphConfig: 設定インスタンス

        Raises:
            MSGraphConfig.DoesNotExist: 設定が存在しない場合
        """
        return self.get(pk=1)


class MSGraphConfig(models.Model):
    """
    Microsoft Graph API設定モデル（シングルトン）

    このモデルは1つのインスタンスのみを持つことを想定しています。
    管理画面から編集可能で、秘密鍵は暗号化して保存されます。
    """

    # Azure AD設定
    tenant_id = models.CharField(
        "テナントID",
        max_length=255,
        help_text="Azure AD（Microsoft Entra ID）のテナントID",
    )
    client_id = models.CharField(
        "クライアントID",
        max_length=255,
        help_text="Azure ADアプリケーションのクライアントID",
    )
    cert_thumbprint = models.CharField(
        "証明書サムプリント",
        max_length=255,
        help_text="証明書のサムプリント（拇印）",
    )
    target_user = models.CharField(
        "対象ユーザー",
        max_length=255,
        help_text="OneDriveにアクセスする対象ユーザーのメールアドレスまたはユーザーID",
    )

    # 暗号化フィールド（秘密鍵）
    _encrypted_private_key = models.TextField(
        "暗号化された秘密鍵",
        blank=True,
        default="",
        db_column="encrypted_private_key",
    )

    # タイムスタンプ
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    objects = MSGraphConfigManager()

    class Meta:
        verbose_name = "API Configuration"
        verbose_name_plural = "Microsoft Graph API"

    def __str__(self):
        return "Microsoft Graph API"

    def save(self, *args, **kwargs):
        """
        保存時にシングルトン制約を強制する
        """
        # pkを常に1に設定（シングルトン）
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def private_key(self) -> str:
        """秘密鍵を復号化して取得"""
        return decrypt_value(self._encrypted_private_key)

    @private_key.setter
    def private_key(self, value: str):
        """秘密鍵を暗号化して保存"""
        self._encrypted_private_key = encrypt_value(value)
