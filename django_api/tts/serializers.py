"""
TTS API用シリアライザ
Swagger UIでパラメータ入力を可能にする
"""

from rest_framework import serializers


class TTSSynthesizeSerializer(serializers.Serializer):
    """音声合成リクエスト用シリアライザ"""

    text = serializers.CharField(
        required=True,
        help_text="合成したいテキスト（セリフ）",
        max_length=500,
    )
    model = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="使用するモデル名（省略時はデフォルトモデル）",
    )
    style = serializers.CharField(
        required=False,
        default="Neutral",
        help_text="スタイル名（例: Neutral, Happy, Sad）",
    )
    style_weight = serializers.FloatField(
        required=False,
        default=1.0,
        min_value=0.0,
        max_value=10.0,
        help_text="スタイルの強さ（0.0-10.0）",
    )
    speed = serializers.FloatField(
        required=False,
        default=1.0,
        min_value=0.5,
        max_value=2.0,
        help_text="話速（0.5-2.0）",
    )
    sdp_ratio = serializers.FloatField(
        required=False,
        default=0.2,
        min_value=0.0,
        max_value=1.0,
        help_text="SDP比率（0.0-1.0）",
    )
    noise_scale = serializers.FloatField(
        required=False,
        default=0.6,
        min_value=0.0,
        max_value=1.0,
        help_text="ノイズスケール（0.0-1.0）",
    )
    noise_scale_w = serializers.FloatField(
        required=False,
        default=0.8,
        min_value=0.0,
        max_value=1.0,
        help_text="ノイズスケールW（0.0-1.0）",
    )
