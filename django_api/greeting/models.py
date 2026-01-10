"""朝のあいさつ設定モデル"""

from typing import Any

from django.core.validators import RegexValidator
from django.db import models


class MorningGreetingConfig(models.Model):
    """朝のあいさつ設定（シングルトン）"""

    # singleton_key は常に 1 で、ユニーク制約により1レコードのみ許可
    singleton_key = models.PositiveSmallIntegerField(default=1, unique=True)

    # 天気設定
    area_code = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^\d{6}$",
                message="予報区コードは6桁の数字で入力してください",
            ),
        ],
        verbose_name="予報区コード",
        help_text="6桁の数字（例: 130010）",
    )

    # TTS設定
    tts_enabled = models.BooleanField(
        default=False, verbose_name="音声合成を有効にする"
    )
    tts_model = models.CharField(
        max_length=100, blank=True, default="", verbose_name="TTSモデル"
    )
    tts_style = models.CharField(
        max_length=50, default="Neutral", verbose_name="TTSスタイル"
    )
    tts_style_weight = models.FloatField(default=1.0, verbose_name="スタイル強度")
    tts_speed = models.FloatField(default=1.0, verbose_name="話速")
    tts_sdp_ratio = models.FloatField(default=0.2, verbose_name="SDP比率")
    tts_noise_scale = models.FloatField(default=0.6, verbose_name="ノイズスケール")
    tts_noise_scale_w = models.FloatField(default=0.8, verbose_name="ノイズスケールW")

    # プロンプト設定
    system_prompt = models.TextField(verbose_name="システムプロンプト")
    user_prompt = models.TextField(verbose_name="ユーザープロンプト")

    class Meta:
        verbose_name = "朝のあいさつ設定"
        verbose_name_plural = "朝のあいさつ設定"

    def __str__(self):
        return "朝のあいさつ設定"

    def save(self, *args, **kwargs):
        """singleton_key を常に 1 に固定し、バリデーションを実行."""
        self.singleton_key = 1
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "MorningGreetingConfig | None":
        """唯一の設定インスタンスを取得（存在しなければ None）."""
        try:
            return cls.objects.get(singleton_key=1)
        except cls.DoesNotExist:
            return None

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
        }
