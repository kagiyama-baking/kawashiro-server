"""
TTS API用カスタムレンダラー
音声データをそのまま返すためのレンダラー
"""

from rest_framework.renderers import BaseRenderer


class AudioWavRenderer(BaseRenderer):
    """WAV音声データ用レンダラー"""

    media_type = "audio/wav"
    format = "wav"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data
