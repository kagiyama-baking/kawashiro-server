"""音声合成の設定項目（機能の設定モデルが継承する抽象モデル）."""

from typing import Any

from django.db import models


class AbstractTTSSettings(models.Model):
    """音声合成の設定項目.

    テーブルは持たず、継承した設定モデル（Talk 設定・Companion 設定）のテーブルに列ができる。
    """

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

    class Meta:
        abstract = True

    def get_tts_options(self) -> dict[str, Any] | None:
        """TTS設定を辞書で取得（無効時は None）.

        キーは `TTSClient.synthesize` のキーワード引数と同じ。
        """
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
