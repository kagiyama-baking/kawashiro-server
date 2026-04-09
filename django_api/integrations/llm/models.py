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


class LLMServiceConfig(models.Model):
    """サービスごとのLLMモデル割り当て設定.

    LiteLLM Proxy経由で使用するモデルをサービス単位で管理する。
    model_aliasはLiteLLM Proxy config.yamlのmodel_nameに対応する。
    """

    SERVICE_CHOICES = [
        ("orchestrator", "HN Agent Orchestrator"),
        ("detective", "HN Agent Detective"),
        ("talk", "Talk（会話生成）"),
        ("embedding", "Embedding生成"),
    ]

    service_name = models.CharField(
        "サービス名",
        max_length=50,
        unique=True,
        choices=SERVICE_CHOICES,
        help_text="LLMを使用するサービスの識別名",
    )
    model_alias = models.CharField(
        "モデルエイリアス",
        max_length=100,
        help_text="LiteLLM Proxyのmodel_name（例: gpt-4o, kimi-k2.5, claude-sonnet）",
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
        return f"{self.get_service_name_display()} → {self.model_alias}"
