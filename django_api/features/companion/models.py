"""Companion の設定モデル."""

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction

from integrations.llm.models import AgentSkill
from integrations.tts.models import AbstractTTSSettings


class CompanionConfigManager(models.Manager):
    """CompanionConfig 用カスタムマネージャー."""

    def get_active_config(self) -> "CompanionConfig":
        """有効な設定を取得.

        システムプロンプト（Prompt）を先読みする。

        Returns:
            CompanionConfig インスタンス

        Raises:
            CompanionConfig.DoesNotExist: 有効な設定が存在しない場合
        """
        return self.select_related("system_prompt").get(is_active=True)


class CompanionConfig(AbstractTTSSettings):
    """Companion 設定（有効にできるのは 1 件だけ）.

    全スキルに共通のシステムプロンプト・天気の予報区・回数の上限・音声合成を持つ。
    スキルは Agent Skills（`AgentSkill`）に登録し、設定では使うものを選ぶ（`skills`）。
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
    system_prompt = models.ForeignKey(
        "llm_config.Prompt",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="システムプロンプト",
        help_text="全スキルに共通のシステムプロンプト（AI設定 → Prompts）",
    )
    skills = models.ManyToManyField(
        AgentSkill,
        blank=True,
        related_name="companion_configs",
        verbose_name="スキル",
        help_text=(
            "この設定で使うスキル（Agent Skills に登録したもの）。"
            "無効にしたスキルは、選んでいても使わない"
        ),
    )
    area_code = models.CharField(
        "予報区コード",
        max_length=10,
        blank=True,
        default="",
        validators=[
            RegexValidator(
                regex=r"^[0-9]{6}\Z",
                message="予報区コードは6桁の数字で入力してください",
            ),
        ],
        help_text="6桁の数字（例: 130010）。天気のツールが使う。空なら天気を取得しない",
    )
    rate_limit = models.PositiveIntegerField(
        "回数の上限（1 分あたり）",
        default=10,
        validators=[MinValueValidator(1)],
        help_text="1 ユーザーが 1 分間に Companion を実行できる回数",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    objects = CompanionConfigManager()

    class Meta:
        verbose_name = "Companion 設定"
        verbose_name_plural = "Companion 設定"

    def __str__(self) -> str:
        if self.is_active:
            return f"{self.name}（有効）"
        return self.name

    def save(self, *args, **kwargs):
        """保存時にバリデーションを実行し、有効な設定が 1 つだけになるようにする.

        ほかの設定の無効化と保存は 1 つのトランザクションで行う（保存に失敗したときに
        有効な設定がなくならないように）。
        """
        self.full_clean()
        with transaction.atomic():
            if self.is_active:
                CompanionConfig.objects.filter(is_active=True).exclude(
                    pk=self.pk
                ).update(is_active=False)
            super().save(*args, **kwargs)
