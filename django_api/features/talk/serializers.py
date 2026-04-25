"""会話生成シリアライザー."""

from rest_framework import serializers


class TalkRequestSerializer(serializers.Serializer):
    """会話生成リクエストのシリアライザー."""

    config_name = serializers.CharField(
        required=True,
        max_length=50,
        help_text="設定名（管理画面で登録した name）",
    )
    user_prompt = serializers.CharField(
        required=False,
        max_length=4000,
        trim_whitespace=False,
        help_text=(
            "ユーザープロンプト（任意、最大 4000 文字）。"
            "指定した場合は Langfuse から取得せず、この文字列を使用する。"
            "`{{weather}}` `{{events}}` `{{datetime}}` のプレースホルダーは展開される。"
        ),
    )


class TalkResponseSerializer(serializers.Serializer):
    """会話生成レスポンスのシリアライザー."""

    greeting_text = serializers.CharField(
        help_text="生成されたテキスト",
    )
    audio_data = serializers.CharField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Base64エンコードされた音声データ（TTS有効時）",
    )
    audio_format = serializers.CharField(
        required=False,
        allow_null=True,
        default=None,
        help_text="音声フォーマット（wav, mp3, ogg）",
    )


class ChatMessageSerializer(serializers.Serializer):
    """チャット 1 メッセージ用シリアライザ."""

    role = serializers.ChoiceField(
        choices=[("user", "user"), ("assistant", "assistant")],
        help_text="メッセージの役割（user / assistant）",
    )
    content = serializers.CharField(
        max_length=4000,
        trim_whitespace=False,
        allow_blank=False,
        help_text="メッセージ本文（最大 4000 文字）",
    )


CHAT_MESSAGES_MAX_COUNT = 50


class ChatRequestSerializer(serializers.Serializer):
    """チャットリクエスト用シリアライザ."""

    config_name = serializers.CharField(
        required=True,
        max_length=50,
        help_text="設定名（管理画面で登録した name）",
    )
    messages = ChatMessageSerializer(
        many=True,
        allow_empty=False,
        help_text=(f"会話履歴（1〜{CHAT_MESSAGES_MAX_COUNT} 件、末尾は role='user'）"),
    )

    def validate_messages(self, value):
        if len(value) > CHAT_MESSAGES_MAX_COUNT:
            raise serializers.ValidationError(
                f"messages は {CHAT_MESSAGES_MAX_COUNT} 件以下にしてください"
            )
        if value[-1]["role"] != "user":
            raise serializers.ValidationError(
                "messages の末尾は role='user' にしてください"
            )
        return value


class ChatResponseSerializer(serializers.Serializer):
    """チャットレスポンス用シリアライザ."""

    message = ChatMessageSerializer(
        help_text="生成された assistant メッセージ",
    )
    audio_data = serializers.CharField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Base64 エンコードされた音声データ（TTS 有効時）",
    )
    audio_format = serializers.CharField(
        required=False,
        allow_null=True,
        default=None,
        help_text="音声フォーマット（wav, mp3, ogg）",
    )


class ConfigItemSerializer(serializers.Serializer):
    """設定一覧の各アイテムのシリアライザー."""

    name = serializers.CharField(help_text="設定名")
    display_name = serializers.CharField(help_text="表示名")
    tts_enabled = serializers.BooleanField(help_text="TTS有効フラグ")


class ConfigListResponseSerializer(serializers.Serializer):
    """設定一覧レスポンスのシリアライザー."""

    configs = ConfigItemSerializer(many=True, help_text="設定一覧")


class TodayInfoResponseSerializer(serializers.Serializer):
    """本日の日時情報レスポンスのシリアライザー."""

    date = serializers.CharField(
        help_text="日付（YYYY-MM-DD形式）",
    )
    time = serializers.CharField(
        help_text="時刻（HH:MM:SS形式）",
    )
    day_of_week = serializers.CharField(
        help_text="曜日（英語）",
    )
    day_of_week_ja = serializers.CharField(
        help_text="曜日（日本語）",
    )
    holiday_name = serializers.CharField(
        allow_null=True,
        help_text="祝日名（祝日でない場合はnull）",
    )
