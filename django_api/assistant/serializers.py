"""アシスタントAPIのシリアライザ."""

from rest_framework import serializers

GREETING_TYPE_CHOICES = [
    ("morning", "朝"),
    ("afternoon", "昼"),
    ("evening", "夜"),
]


class GreetingRequestSerializer(serializers.Serializer):
    """挨拶生成リクエストのシリアライザ."""

    area_code = serializers.CharField(
        required=False,
        allow_null=True,
        default=None,
        help_text="予報区コード（6桁）。例: 130010=東京地方。指定時のみ天気を取得",
    )
    greeting_type = serializers.ChoiceField(
        choices=GREETING_TYPE_CHOICES,
        default="morning",
        help_text="挨拶タイプ（morning: 朝, afternoon: 昼, evening: 夜）",
    )
    include_audio = serializers.BooleanField(
        default=False,
        help_text="音声データを含めるか",
    )


class GreetingResponseSerializer(serializers.Serializer):
    """挨拶生成レスポンスのシリアライザ."""

    text = serializers.CharField(
        read_only=True,
        help_text="生成された挨拶テキスト",
    )
    events_count = serializers.IntegerField(
        read_only=True,
        help_text="今日の予定件数",
    )
    weather_summary = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="天気サマリー（area_code指定時のみ）",
    )
    thinking = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="エージェントの思考内容",
    )
    tools_used = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
        help_text="使用されたツール名のリスト",
    )
    audio = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="data URI形式の音声データ（data:audio/wav;base64,...）",
    )


class ChatRequestSerializer(serializers.Serializer):
    """チャットリクエストのシリアライザ."""

    message = serializers.CharField(
        required=True,
        max_length=1000,
        help_text="ユーザーメッセージ",
    )
    area_code = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="天気取得用の予報区コード（オプション）",
    )
    include_audio = serializers.BooleanField(
        default=False,
        help_text="音声データを含めるか",
    )


class ChatResponseSerializer(serializers.Serializer):
    """チャットレスポンスのシリアライザ."""

    reply = serializers.CharField(
        read_only=True,
        help_text="アシスタントの回答",
    )
    tools_used = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
        help_text="使用されたツール名のリスト",
    )
    audio = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="Base64エンコードされた音声データ（WAV形式）",
    )


class DailySummaryRequestSerializer(serializers.Serializer):
    """日次サマリーリクエストのシリアライザ."""

    area_code = serializers.CharField(
        required=True,
        help_text="予報区コード（6桁）。例: 130010=東京地方",
    )
    include_audio = serializers.BooleanField(
        default=False,
        help_text="音声データを含めるか",
    )


class DailySummaryResponseSerializer(serializers.Serializer):
    """日次サマリーレスポンスのシリアライザ."""

    summary = serializers.CharField(
        read_only=True,
        help_text="生成されたサマリーテキスト",
    )
    date = serializers.CharField(
        read_only=True,
        help_text="サマリー対象日（YYYY-MM-DD形式）",
    )
    audio = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="Base64エンコードされた音声データ（WAV形式）",
    )
