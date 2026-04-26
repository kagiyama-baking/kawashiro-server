"""会話生成設定モデル"""

import uuid
from typing import Any

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


def chat_audio_upload_path(instance: "ChatMessage", filename: str) -> str:
    """ChatMessage の audio_file 保存先パス."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "wav"
    return f"talk_audio/{instance.session_id}/{instance.sequence}.{ext}"


class TalkConfig(models.Model):
    """挨拶設定"""

    # 識別子
    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="設定名",
        help_text="API呼び出し時に指定する識別子（例: morning, evening）",
    )
    display_name = models.CharField(
        max_length=100,
        verbose_name="表示名",
        help_text="管理画面での表示名",
    )

    # 天気設定
    area_code = models.CharField(
        max_length=10,
        blank=True,
        default="",
        validators=[
            RegexValidator(
                regex=r"^\d{6}$",
                message="予報区コードは6桁の数字で入力してください",
            ),
        ],
        verbose_name="予報区コード",
        help_text=(
            "6桁の数字（例: 130010）。プロンプトに `{{weather}}` を含める場合は必須"
        ),
    )

    # TTS設定
    tts_enabled = models.BooleanField(
        default=False,
        verbose_name="音声合成を有効にする",
    )
    tts_model = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="TTSモデル",
    )
    tts_style = models.CharField(
        max_length=50,
        default="Neutral",
        verbose_name="TTSスタイル",
    )
    tts_style_weight = models.FloatField(
        default=1.0,
        verbose_name="スタイル強度",
    )
    tts_speed = models.FloatField(
        default=1.0,
        verbose_name="話速",
    )
    tts_sdp_ratio = models.FloatField(
        default=0.2,
        verbose_name="SDP比率",
    )
    tts_noise_scale = models.FloatField(
        default=0.6,
        verbose_name="ノイズスケール",
    )
    tts_noise_scale_w = models.FloatField(
        default=0.8,
        verbose_name="ノイズスケールW",
    )
    tts_format = models.CharField(
        max_length=10,
        default="wav",
        choices=[("wav", "WAV"), ("mp3", "MP3"), ("ogg", "OGG")],
        verbose_name="音声フォーマット",
        help_text="出力音声のフォーマット（デフォルト: WAV）",
    )

    # プロンプト参照（Langfuse 管理）
    system_prompt_ref = models.ForeignKey(
        "langfuse_integration.LangfusePromptRef",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="システムプロンプト",
        help_text="システムプロンプトの Langfuse参照",
    )
    user_prompt_ref = models.ForeignKey(
        "langfuse_integration.LangfusePromptRef",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="ユーザープロンプト",
        help_text="ユーザープロンプトテンプレートの Langfuse参照",
    )

    class Meta:
        db_table = "talk_talkconfig"
        verbose_name = "会話生成設定"
        verbose_name_plural = "会話生成設定"

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        """保存時にバリデーションを実行."""
        self.full_clean()
        super().save(*args, **kwargs)

    def get_tts_options(self) -> dict[str, Any] | None:
        """TTS設定を辞書で取得（無効時は None）."""
        if not self.tts_enabled:
            return None

        return {
            "model": self.tts_model or None,
            "style": self.tts_style,
            "style_weight": self.tts_style_weight,
            "speed": self.tts_speed,
            "sdp_ratio": self.tts_sdp_ratio,
            "noise_scale": self.tts_noise_scale,
            "noise_scale_w": self.tts_noise_scale_w,
            "format": self.tts_format,
        }


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
    config_name = models.CharField(
        max_length=50,
        verbose_name="プリセット名",
        help_text="セッション作成時に固定。途中変更不可",
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
