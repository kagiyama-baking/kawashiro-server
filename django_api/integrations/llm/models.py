"""LLM API設定モデル."""

from django.db import models

from core.encryption import decrypt_value, encrypt_value


class LLMProviderConfig(models.Model):
    """LLMプロバイダー設定（モデル + Virtual Key）.

    モデルエイリアスとAPIキーの組み合わせを管理する。
    複数のLLMServiceConfigから共有して参照できる。
    """

    name = models.CharField(
        "設定名",
        max_length=100,
        unique=True,
        help_text="この設定の識別名（例: Kimi K2.5 本番, GPT-4o テスト）",
    )
    model_alias = models.CharField(
        "モデルエイリアス",
        max_length=100,
        help_text="LiteLLM Proxyのmodel_name（例: bedrock/moonshotai.kimi-k2.5）",
    )
    _encrypted_proxy_api_key = models.TextField(
        "暗号化されたAPIキー",
        blank=True,
        default="",
        db_column="encrypted_proxy_api_key",
        help_text="LiteLLM Virtual Key（未設定時はLITELLM_MASTER_KEY環境変数を使用）",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "LLM設定"
        verbose_name_plural = "LLM設定"

    def __str__(self):
        return f"{self.name}（{self.model_alias}）"

    @property
    def proxy_api_key(self) -> str:
        """Virtual Keyを復号化して取得（未設定時は空文字列）."""
        return decrypt_value(self._encrypted_proxy_api_key)

    @proxy_api_key.setter
    def proxy_api_key(self, value: str):
        """Virtual Keyを暗号化して保存."""
        self._encrypted_proxy_api_key = encrypt_value(value)


class LLMServiceConfig(models.Model):
    """サービスごとのLLM設定割り当て.

    各サービスがどのLLMプロバイダー設定を使用するかを管理する。
    """

    SERVICE_CHOICES = [
        ("orchestrator", "HN Agent Orchestrator"),
        ("detective", "HN Agent Detective"),
        ("devils_advocate", "HN Agent Devil's Advocate"),
        ("security_responder", "HN Agent Security Responder"),
        ("talk", "Talk Generator"),
    ]

    service_name = models.CharField(
        "サービス名",
        max_length=50,
        unique=True,
        choices=SERVICE_CHOICES,
        help_text="LLMを使用するサービスの識別名",
    )
    provider_config = models.ForeignKey(
        LLMProviderConfig,
        on_delete=models.PROTECT,
        verbose_name="LLM設定",
        help_text="使用するLLMプロバイダー設定を選択",
    )
    is_active = models.BooleanField(
        "有効",
        default=True,
        help_text="このサービス設定を有効にする",
    )
    timeout = models.IntegerField(
        "タイムアウト（秒）",
        default=60,
        help_text="APIリクエストのタイムアウト秒数",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "LLMサービス設定"
        verbose_name_plural = "LLMサービス設定"

    def __str__(self):
        return f"{self.get_service_name_display()} → {self.provider_config.name}"
