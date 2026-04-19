"""会話生成設定モデル"""

from typing import Any

from django.core.validators import RegexValidator
from django.db import models


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
