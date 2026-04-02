"""Slack通知設定モデル."""

from django.db import models

from core.encryption import decrypt_value, encrypt_value


class SlackConfigManager(models.Manager):
    """SlackConfig用カスタムマネージャー."""

    def get_active_config(self):
        """有効な設定を取得.

        Returns:
            SlackConfigインスタンス

        Raises:
            SlackConfig.DoesNotExist: 有効な設定が存在しない場合
        """
        return self.get(is_active=True)


class SlackConfig(models.Model):
    """Slack Webhook設定モデル.

    複数の設定を保存でき、そのうち1つだけを有効にできます。
    管理画面から編集可能で、Webhook URLは暗号化して保存されます。
    """

    name = models.CharField(
        "設定名",
        max_length=255,
        unique=True,
        help_text="この設定を識別するための名前（例：HN通知チャンネル）",
    )
    is_active = models.BooleanField(
        "有効",
        default=False,
        help_text="この設定を有効にする（有効にできるのは1つの設定のみ）",
    )
    _encrypted_webhook_url = models.TextField(
        "暗号化されたWebhook URL",
        blank=True,
        default="",
        db_column="encrypted_webhook_url",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    objects = SlackConfigManager()

    class Meta:
        verbose_name = "Slack通知設定"
        verbose_name_plural = "Slack通知設定"

    def __str__(self):
        if self.is_active:
            return f"{self.name}（有効）"
        return self.name

    @property
    def webhook_url(self) -> str:
        """Webhook URLを復号化して取得."""
        return decrypt_value(self._encrypted_webhook_url)

    @webhook_url.setter
    def webhook_url(self, value: str):
        """Webhook URLを暗号化して保存."""
        self._encrypted_webhook_url = encrypt_value(value)

    def save(self, *args, **kwargs):
        """保存時にバリデーション実行、有効な設定が1つだけになるようにする."""
        self.full_clean()
        if self.is_active:
            SlackConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )
        super().save(*args, **kwargs)
