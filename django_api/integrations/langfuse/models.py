"""Langfuseプロンプト参照モデル."""

from django.db import models


class LangfusePromptRef(models.Model):
    """Langfuse上のプロンプト参照.

    Langfuseで管理しているプロンプトへの参照を Django 側で保持する。
    実体は Langfuse 側にあり、このモデルは名前・ラベル・フォールバックのみ持つ。

    各機能（HN Agent, Talk 等）は用途ごとにこのモデルへの ForeignKey を持ち、
    プロンプト解決時は `integrations.langfuse.client.resolve_prompt` を使う。
    """

    name = models.CharField(
        "識別名",
        max_length=100,
        unique=True,
        help_text="Django 内で一意に識別する名前（例: hn-agent-orchestrator-system）",
    )
    langfuse_prompt_name = models.CharField(
        "Langfuseプロンプト名",
        max_length=200,
        help_text="Langfuse 上で登録されているプロンプト名",
    )
    label = models.CharField(
        "ラベル",
        max_length=50,
        default="production",
        help_text="Langfuse のプロンプトラベル（production, staging 等）",
    )
    fallback_text = models.TextField(
        "フォールバックテキスト",
        blank=True,
        default="",
        help_text="Langfuse 接続失敗・プロンプト未登録時に使用するテキスト",
    )
    description = models.CharField(
        "説明",
        max_length=255,
        blank=True,
        default="",
        help_text="このプロンプトの用途説明",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "Langfuseプロンプト参照"
        verbose_name_plural = "Langfuseプロンプト参照"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.langfuse_prompt_name}@{self.label})"
