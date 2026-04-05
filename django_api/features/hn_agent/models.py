"""HN Agentデータモデル."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from pgvector.django import VectorField


class HNThread(models.Model):
    """Hacker Newsスレッド."""

    hn_id = models.IntegerField(
        unique=True,
        db_index=True,
        verbose_name="HN ID",
        help_text="Hacker NewsのアイテムID",
    )
    title = models.TextField(
        verbose_name="タイトル",
    )
    url = models.URLField(
        max_length=2048,
        blank=True,
        default="",
        verbose_name="URL",
        help_text="外部リンクURL（self-postの場合は空）",
    )
    author = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="投稿者",
    )
    is_investigated = models.BooleanField(
        default=False,
        verbose_name="調査済み",
        help_text="エージェントによる調査が完了しているか",
    )
    first_seen = models.DateTimeField(
        auto_now_add=True,
        verbose_name="初回検出日時",
    )

    class Meta:
        verbose_name = "HNスレッド"
        verbose_name_plural = "HNスレッド"
        ordering = ["-first_seen"]

    def __str__(self):
        return f"[{self.hn_id}] {self.title}"

    @property
    def latest_snapshot(self) -> "HNThreadSnapshot | None":
        """最新のスナップショットを取得."""
        return self.snapshots.order_by("-fetched_at").first()


class HNThreadSnapshot(models.Model):
    """HNスレッドのスコア・コメント数の時系列スナップショット."""

    thread = models.ForeignKey(
        HNThread,
        on_delete=models.CASCADE,
        related_name="snapshots",
        verbose_name="スレッド",
    )
    score = models.IntegerField(
        verbose_name="スコア",
    )
    num_comments = models.IntegerField(
        verbose_name="コメント数",
    )
    fetched_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="取得日時",
    )

    class Meta:
        verbose_name = "スナップショット"
        verbose_name_plural = "スナップショット"
        ordering = ["-fetched_at"]
        indexes = [
            models.Index(fields=["thread", "fetched_at"]),
        ]

    def __str__(self):
        return f"{self.thread.hn_id}: score={self.score}, comments={self.num_comments} @ {self.fetched_at}"


class ThreadEmbedding(models.Model):
    """調査対象スレッドのembedding（pgvector）."""

    thread = models.OneToOneField(
        HNThread,
        on_delete=models.CASCADE,
        related_name="embedding",
        verbose_name="スレッド",
    )
    embedding = VectorField(
        verbose_name="埋め込みベクトル",
        help_text="次元数はHN Agent設定のembedding_dimensionsに依存",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="作成日時",
    )

    class Meta:
        verbose_name = "スレッド埋め込み"
        verbose_name_plural = "スレッド埋め込み"

    def __str__(self):
        return f"Embedding: [{self.thread.hn_id}] {self.thread.title}"


class Investigation(models.Model):
    """エージェント調査結果."""

    AGENT_TYPES = [
        ("detective", "Detective"),
        ("memory", "Memory"),
    ]

    thread = models.ForeignKey(
        HNThread,
        on_delete=models.CASCADE,
        related_name="investigations",
        verbose_name="スレッド",
    )
    agent_type = models.CharField(
        max_length=50,
        choices=AGENT_TYPES,
        verbose_name="エージェント種別",
    )
    result = models.JSONField(
        verbose_name="調査結果",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="作成日時",
    )

    class Meta:
        verbose_name = "調査結果"
        verbose_name_plural = "調査結果"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.agent_type}: [{self.thread.hn_id}] {self.thread.title}"


class HNAgentConfigManager(models.Manager):
    """HNAgentConfig用カスタムマネージャー."""

    def get_active_config(self):
        """有効な設定を取得.

        Returns:
            HNAgentConfigインスタンス

        Raises:
            HNAgentConfig.DoesNotExist: 有効な設定が存在しない場合
        """
        return self.get(is_active=True)


class HNAgentConfig(models.Model):
    """HN Agent設定モデル.

    エージェントの動作パラメータ（閾値、ポーリング間隔等）を管理画面から設定する。
    LLMのAPIキーやモデル名はOpenAI API設定で管理する。
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
    reasoning_effort = models.CharField(
        "推論深度",
        max_length=10,
        default="low",
        blank=True,
        choices=[
            ("", "無効（モデル非対応時）"),
            ("low", "低（ツール選択等の単純判断向け）"),
            ("medium", "中"),
            ("high", "高（複雑な判断向け）"),
        ],
        help_text="Orchestratorの推論トークン量を制御（コストに影響）。モデルが非対応の場合は「無効」を選択",
    )
    embedding_dimensions = models.IntegerField(
        "Embedding次元数",
        default=1536,
        validators=[MinValueValidator(1), MaxValueValidator(3072)],
        help_text=(
            "Embedding APIに渡す出力次元数。"
            "DBのベクトルカラムもこの値に合わせる必要がある。"
            "text-embedding-3-small: 最大1536、text-embedding-3-large: 最大3072"
        ),
    )
    score_threshold = models.IntegerField(
        "スコア閾値",
        default=100,
        validators=[MinValueValidator(1)],
        help_text="調査をトリガーするスコアの閾値",
    )
    velocity_threshold = models.FloatField(
        "速度閾値（ポイント/時間）",
        default=50.0,
        validators=[MinValueValidator(0.1)],
        help_text="調査をトリガーするスコア上昇速度の閾値",
    )
    similarity_threshold = models.FloatField(
        "類似度閾値",
        default=0.85,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="過去スレッド検索のcosine similarity閾値（0-1）",
    )
    poll_interval_seconds = models.IntegerField(
        "ポーリング間隔（秒）",
        default=600,
        validators=[MinValueValidator(60)],
        help_text="HNフロントページのポーリング間隔（最低60秒）",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    objects = HNAgentConfigManager()

    class Meta:
        verbose_name = "HN Agent設定"
        verbose_name_plural = "HN Agent設定"

    def __str__(self):
        if self.is_active:
            return f"{self.name}（有効）"
        return self.name

    def save(self, *args, **kwargs):
        """保存時にバリデーション実行、有効な設定が1つだけになるようにする."""
        self.full_clean()
        if self.is_active:
            HNAgentConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )
        super().save(*args, **kwargs)
