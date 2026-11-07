"""Talk のモデル（Talk 設定・チャット履歴）."""

import uuid
from typing import Any

from django.conf import settings
from django.db import models

from integrations.llm.models import AgentSkill
from integrations.tts.models import AbstractTTSSettings


def chat_audio_upload_path(instance: "ChatMessage", filename: str) -> str:
    """ChatMessage の audio_file 保存先パス."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "wav"
    return f"talk_audio/{instance.session_id}/{instance.sequence}.{ext}"


class TalkSetting(AbstractTTSSettings):
    """Talk 設定（チャットのシステムプロンプト・選べるシーン・音声）.

    複数を有効にでき、有効な設定をフロントの Talk で選ぶ。シーンは Agent Skills
    （AgentSkill）から選び、チャットでは選んだシーンの本文をシステムプロンプトの後ろに足す。
    ツールは使わない。
    """

    name = models.CharField(
        "設定名",
        max_length=255,
        unique=True,
        help_text="フロントの Talk で選ぶときに出る名前",
    )
    is_enabled = models.BooleanField(
        "有効",
        default=True,
        help_text=(
            "有効な設定だけを、フロントの Talk で選べて続けて話せる。"
            "複数の設定を有効にできる"
        ),
    )
    system_prompt = models.ForeignKey(
        "llm_config.Prompt",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="システムプロンプト",
        help_text=(
            "チャットのシステムプロンプト（AI設定 → Prompts）。"
            "変数（{{weather}} など）は展開しない"
        ),
    )
    skills = models.ManyToManyField(
        AgentSkill,
        blank=True,
        related_name="talk_settings",
        verbose_name="シーン",
        help_text=(
            "この設定で選べるシーン（Agent Skills に登録したもの）。"
            "無効にしたスキルは、選んでいてもフロントでは選べない。"
            "シーンの本文はツールを前提にしない"
        ),
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Talk 設定"
        verbose_name_plural = "Talk 設定"

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """保存時にバリデーションを実行."""
        self.full_clean()
        super().save(*args, **kwargs)


class ChatSession(models.Model):
    """チャットセッション（履歴）."""

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
        verbose_name="ユーザー",
    )
    title = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="タイトル",
        help_text="初回応答後に LLM で要約生成。手動編集も可能",
    )
    setting = models.ForeignKey(
        TalkSetting,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="chat_sessions",
        verbose_name="Talk 設定",
        help_text=(
            "セッション作成時に固定。チャットで使った設定は消せない（無効にする）"
        ),
    )
    skill = models.ForeignKey(
        AgentSkill,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="talk_chat_sessions",
        verbose_name="シーン",
        help_text=(
            "セッション作成時に固定（シーンなしなら空）。"
            "チャットで使ったスキルは消せない（無効にする）"
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "talk_chatsession"
        ordering = ["-updated_at"]
        verbose_name = "チャットセッション"
        verbose_name_plural = "チャットセッション"
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return self.title or f"ChatSession({self.id})"


class ChatMessage(models.Model):
    """チャットメッセージ（user / assistant）."""

    ROLE_CHOICES = [
        (ChatSession.ROLE_USER, "user"),
        (ChatSession.ROLE_ASSISTANT, "assistant"),
    ]

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sequence = models.PositiveIntegerField(verbose_name="セッション内の連番")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    audio_file = models.FileField(
        upload_to=chat_audio_upload_path,
        null=True,
        blank=True,
        verbose_name="音声ファイル",
    )
    audio_format = models.CharField(max_length=10, blank=True, default="")
    audio_size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "talk_chatmessage"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "sequence"],
                name="uniq_chatmessage_session_sequence",
            ),
        ]
        verbose_name = "チャットメッセージ"
        verbose_name_plural = "チャットメッセージ"

    def __str__(self) -> str:
        return f"{self.role}#{self.sequence} ({self.session_id})"
