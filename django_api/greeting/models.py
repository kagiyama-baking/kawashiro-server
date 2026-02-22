"""挨拶設定モデル"""

from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class GreetingConfig(models.Model):
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

    # プレースホルダー設定
    use_weather = models.BooleanField(
        default=False,
        verbose_name="天気情報を使用",
        help_text="{{weather}} プレースホルダーを有効にする",
    )
    use_events = models.BooleanField(
        default=False,
        verbose_name="予定情報を使用",
        help_text="{{events}} プレースホルダーを有効にする",
    )
    use_datetime = models.BooleanField(
        default=True,
        verbose_name="日時情報を使用",
        help_text="{{datetime}} プレースホルダーを有効にする",
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
        help_text="6桁の数字（例: 130010）。天気情報を使用する場合は必須",
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

    # プロンプト設定
    system_prompt = models.TextField(
        verbose_name="システムプロンプト",
    )

    class Meta:
        verbose_name = "挨拶設定"
        verbose_name_plural = "挨拶設定"

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        """保存時にバリデーションを実行."""
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        """バリデーション."""
        super().clean()

        # use_weather=True の場合、area_code は必須
        if self.use_weather and not self.area_code:
            raise ValidationError(
                {"area_code": "天気情報を使用する場合は予報区コードが必須です"}
            )

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

    def get_enabled_placeholders(self) -> list[str]:
        """有効なプレースホルダーのリストを取得."""
        placeholders = []
        if self.use_weather:
            placeholders.append("weather")
        if self.use_events:
            placeholders.append("events")
        if self.use_datetime:
            placeholders.append("datetime")
        return placeholders
