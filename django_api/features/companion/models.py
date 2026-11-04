"""Companion の設定モデル."""

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction

from integrations.tts.models import AbstractTTSSettings

# スキル名の規則（Agent Skills の命名: 英小文字・数字・ハイフン。先頭・末尾・連続のハイフンは不可）。
# スキル名は PydanticAI の capability の id になるので、id に使えない `:` も、予約の
# `deferred_capabilities` も通らない。`$` は末尾の改行も通すので `\Z` で終える。
SKILL_NAME_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*\Z"

# 毎回の実行に入る組み込みの capability の id（`integrations/llm/apps.py` の
# `Agent.instrument_all` が入れる Instrumentation）。スキル名が同じだと id が衝突し、
# そのスキルを渡した実行は始まる前に失敗する。
RESERVED_SKILL_NAMES = frozenset({"instrumentation"})


def validate_skill_name_not_reserved(value: str) -> None:
    """組み込みの capability と同じ id になるスキル名を拒む."""
    if value in RESERVED_SKILL_NAMES:
        raise ValidationError(
            "「%(value)s」は予約されているため、スキル名に使えません",
            code="reserved",
            params={"value": value},
        )


class CompanionConfigManager(models.Manager):
    """CompanionConfig 用カスタムマネージャー."""

    def get_active_config(self) -> "CompanionConfig":
        """有効な設定を取得.

        システムプロンプトの参照を先読みする。

        Returns:
            CompanionConfig インスタンス

        Raises:
            CompanionConfig.DoesNotExist: 有効な設定が存在しない場合
        """
        return self.select_related("system_prompt_ref").get(is_active=True)


class CompanionConfig(AbstractTTSSettings):
    """Companion 設定（有効にできるのは 1 件だけ）.

    全スキルに共通のシステムプロンプト・天気の予報区・回数の上限・音声合成を持つ。
    スキルは `CompanionSkill`（`skills`）として設定ごとに登録する。
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
    system_prompt_ref = models.ForeignKey(
        "langfuse_integration.LangfusePromptRef",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="システムプロンプト",
        help_text="全スキルに共通のシステムプロンプトの Langfuse参照",
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


class CompanionSkill(models.Model):
    """Companion のスキル（用途ごとの手順）.

    名前と説明はモデルに見せる一覧になり、本文（Langfuse の text プロンプト）は
    そのスキルを使うときだけ読む。
    """

    config = models.ForeignKey(
        CompanionConfig,
        on_delete=models.CASCADE,
        related_name="skills",
        verbose_name="Companion 設定",
    )
    name = models.CharField(
        "スキル名",
        max_length=64,
        validators=[
            RegexValidator(
                regex=SKILL_NAME_PATTERN,
                message=(
                    "スキル名は英小文字・数字をハイフンでつないだ形で入力してください"
                    "（例: good-morning）"
                ),
            ),
            validate_skill_name_not_reserved,
        ],
        help_text=(
            "英小文字・数字・ハイフン（例: good-morning）、64 字以内。"
            "先頭・末尾・連続のハイフンは使えない"
        ),
    )
    description = models.CharField(
        "説明",
        max_length=1024,
        help_text=(
            "どんな発話のときに使うスキルか（例: 朝のあいさつ。「おはよう」など）。"
            "モデルはこの説明を読んで使うスキルを選ぶ。1024 字以内"
        ),
    )
    prompt_ref = models.ForeignKey(
        "langfuse_integration.LangfusePromptRef",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="本文",
        help_text="スキルの手順（本文）の Langfuse参照",
    )
    is_enabled = models.BooleanField(
        "有効",
        default=True,
        help_text="無効にしたスキルは使わない",
    )

    class Meta:
        verbose_name = "スキル"
        verbose_name_plural = "スキル"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["config", "name"],
                name="companion_skill_unique_name_per_config",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        """保存時にバリデーションを実行."""
        self.full_clean()
        super().save(*args, **kwargs)
