"""Tavily API設定モデル."""

from django.db import models

from core.encryption import decrypt_value, encrypt_value


class TavilyConfigManager(models.Manager):
    """TavilyConfig用カスタムマネージャー."""

    def get_active_config(self):
        """有効な設定を取得.

        Returns:
            TavilyConfigインスタンス

        Raises:
            TavilyConfig.DoesNotExist: 有効な設定が存在しない場合
        """
        return self.get(is_active=True)


class TavilyConfig(models.Model):
    """Tavily API設定モデル.

    複数の設定を保存でき、そのうち1つだけを有効にできます。
    管理画面から編集可能で、APIキーは暗号化して保存されます。
    """

    name = models.CharField(
        "設定名",
        max_length=255,
        unique=True,
        help_text="この設定を識別するための名前",
    )
    is_active = models.BooleanField(
        "有効",
        default=False,
        help_text="この設定を有効にする（有効にできるのは1つの設定のみ）",
    )
    _encrypted_api_key = models.TextField(
        "暗号化されたAPIキー",
        blank=True,
        default="",
        db_column="encrypted_api_key",
    )
    timeout = models.IntegerField(
        "タイムアウト（秒）",
        default=30,
        help_text="APIリクエストのタイムアウト秒数",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    objects = TavilyConfigManager()

    class Meta:
        verbose_name = "Tavily API設定"
        verbose_name_plural = "Tavily API設定"

    def __str__(self):
        if self.is_active:
            return f"{self.name}（有効）"
        return self.name

    def save(self, *args, **kwargs):
        """保存時にバリデーション実行、有効な設定が1つだけになるようにする."""
        self.full_clean()
        if self.is_active:
            TavilyConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )
        super().save(*args, **kwargs)

    @property
    def api_key(self) -> str:
        """APIキーを復号化して取得."""
        return decrypt_value(self._encrypted_api_key)

    @api_key.setter
    def api_key(self, value: str):
        """APIキーを暗号化して保存."""
        self._encrypted_api_key = encrypt_value(value)
