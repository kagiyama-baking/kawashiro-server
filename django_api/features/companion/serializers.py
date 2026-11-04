"""Companion の実行 API のシリアライザー."""

import base64

from rest_framework import serializers

from .models import SKILL_NAME_PATTERN, AgentSkill
from .services import CompanionReply

# 発話の最大文字数
PROMPT_MAX_LENGTH = 1000


class CompanionRunRequestSerializer(serializers.Serializer):
    """Companion の実行リクエスト."""

    prompt = serializers.CharField(
        max_length=PROMPT_MAX_LENGTH,
        # Talk の発話の入力と同じく、前後の空白・改行も除かずにそのまま渡す
        trim_whitespace=False,
        help_text=(
            f"発話（例: おはよう）。1〜{PROMPT_MAX_LENGTH} 文字で、空白だけは不可。"
            "前後の空白も含めてそのまま渡す"
        ),
    )
    skill = serializers.RegexField(
        SKILL_NAME_PATTERN,
        max_length=AgentSkill._meta.get_field("name").max_length,
        required=False,
        allow_null=True,
        error_messages={
            "invalid": (
                "スキル名は英小文字・数字をハイフンでつないだ形で指定してください"
                "（例: good-morning）"
            ),
        },
        help_text=(
            "使うスキルの名前（例: good-morning）。省略か null なら、"
            "エージェントが発話に合うスキルを選ぶ"
        ),
    )

    def validate_prompt(self, value: str) -> str:
        """空白だけの発話も、空の発話として拒む."""
        if not value.strip():
            self.fields["prompt"].fail("blank")
        return value


class CompanionRunResponseSerializer(serializers.Serializer):
    """Companion の実行結果（`CompanionReply`）の応答."""

    text = serializers.CharField(help_text="セリフ（前後の空白を除いたもの）")
    skill = serializers.CharField(
        allow_null=True, help_text="使ったスキルの名前（使わなかったときは null）"
    )
    audio_data = serializers.CharField(
        allow_null=True,
        help_text="Base64 でエンコードした音声（音声合成が無効なら null）",
    )
    audio_format = serializers.CharField(
        allow_null=True,
        help_text="音声の形式（wav / mp3 / ogg。音声合成が無効なら null）",
    )

    def to_representation(self, instance: CompanionReply) -> dict:
        """実行結果を応答の形にする（音声のバイト列は Base64 の文字列にする）."""
        audio = instance.audio
        return super().to_representation(
            {
                "text": instance.text,
                "skill": instance.skill,
                "audio_data": (
                    None
                    if audio is None
                    else base64.b64encode(audio.audio_data).decode("ascii")
                ),
                "audio_format": None if audio is None else audio.format,
            }
        )
