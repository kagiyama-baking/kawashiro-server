"""Microsoft Graph API設定モデル"""

from django.db import models

from core.encryption import decrypt_value, encrypt_value


class MSGraphConfigManager(models.Manager):
    """MSGraphConfigのカスタムマネージャー"""

    def get_active_config(self):
        """
        有効な設定を取得する

        Returns:
            MSGraphConfig: 有効な設定インスタンス

        Raises:
            MSGraphConfig.DoesNotExist: 有効な設定が存在しない場合
        """
        return self.get(is_active=True)


class MSGraphConfig(models.Model):
    """
    Microsoft Graph API設定モデル

    複数の設定を保存でき、そのうち1つだけを有効にできます。
    管理画面から編集可能で、秘密鍵は暗号化して保存されます。
    """

    # 設定名
    name = models.CharField(
        "設定名",
        max_length=255,
        unique=True,
        default="デフォルト設定",
        help_text="この設定を識別するための名前（例：本番環境、テスト環境）",
    )

    # 有効/無効フラグ
    is_active = models.BooleanField(
        "有効",
        default=False,
        help_text="この設定を有効にする（有効にできるのは1つの設定のみ）",
    )

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
        help_text="Microsoft Graph APIでアクセスする対象ユーザーのメールアドレスまたはユーザーID",
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
        verbose_name = "Microsoft Graph API設定"
        verbose_name_plural = "Microsoft Graph API設定"

    def __str__(self):
        if self.is_active:
            return f"{self.name}（有効）"
        return self.name

    def save(self, *args, **kwargs):
        """
        保存時に有効な設定が1つだけになるようにする
        """
        if self.is_active:
            # 他の有効な設定を無効にする
            MSGraphConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )
        super().save(*args, **kwargs)

    @property
    def private_key(self) -> str:
        """秘密鍵を復号化して取得"""
        return decrypt_value(self._encrypted_private_key)

    @private_key.setter
    def private_key(self, value: str):
        """秘密鍵を暗号化して保存"""
        self._encrypted_private_key = encrypt_value(value)
