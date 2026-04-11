"""LLM API設定モデル."""

from django.db import models

from core.encryption import decrypt_value, encrypt_value


class BaseLLMConfigManager(models.Manager):
    """LLM設定の基底マネージャー"""

    def get_active_config(self):
        """
        有効な設定を取得する

        Returns:
            設定インスタンス

        Raises:
            DoesNotExist: 有効な設定が存在しない場合
        """
        return self.get(is_active=True)


class BaseLLMConfig(models.Model):
    """
    LLM API設定の基底モデル

    各LLMプロバイダー（OpenAI、Gemini、Claude等）の
    設定モデルはこのクラスを継承します。
    """

    # 設定名
    name = models.CharField(
        "設定名",
        max_length=255,
        unique=True,
        help_text="この設定を識別するための名前（例：本番環境、テスト環境）",
    )

    # 有効/無効フラグ
    is_active = models.BooleanField(
        "有効",
        default=False,
        help_text="この設定を有効にする（有効にできるのは1つの設定のみ）",
    )

    # タイムアウト設定
    timeout = models.IntegerField(
        "タイムアウト（秒）",
        default=60,
        help_text="APIリクエストのタイムアウト秒数",
    )

    # 暗号化フィールド（APIキー）
    _encrypted_api_key = models.TextField(
        "暗号化されたAPIキー",
        blank=True,
        default="",
        db_column="encrypted_api_key",
    )

    # タイムスタンプ
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        if self.is_active:
            return f"{self.name}（有効）"
        return self.name

    @property
    def api_key(self) -> str:
        """APIキーを復号化して取得"""
        return decrypt_value(self._encrypted_api_key)

    @api_key.setter
    def api_key(self, value: str):
        """APIキーを暗号化して保存"""
        self._encrypted_api_key = encrypt_value(value)


class OpenAIConfigManager(BaseLLMConfigManager):
    """OpenAIConfigのカスタムマネージャー"""


class OpenAIConfig(BaseLLMConfig):
    """
    OpenAI API設定モデル

    複数の設定を保存でき、そのうち1つだけを有効にできます。
    管理画面から編集可能で、APIキーは暗号化して保存されます。
    """

    # モデル設定
    model = models.CharField(
        "チャットモデル",
        max_length=255,
        default="gpt-4o-mini",
        help_text="チャット補完に使用するモデル（例：gpt-4o-mini, gpt-4o）",
    )

    embedding_model = models.CharField(
        "Embeddingモデル",
        max_length=255,
        default="text-embedding-3-small",
        help_text="Embedding生成に使用するモデル（例：text-embedding-3-small）",
    )

    objects = OpenAIConfigManager()

    class Meta:
        verbose_name = "OpenAI API設定"
        verbose_name_plural = "OpenAI API設定"

    def save(self, *args, **kwargs):
        """保存時に有効な設定が1つだけになるようにする."""
        if self.is_active:
            # 他の有効な設定を無効にする
            OpenAIConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )
        super().save(*args, **kwargs)


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
        ("talk", "Talk（会話生成）"),
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
