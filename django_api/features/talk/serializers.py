"""Talk のシリアライザー（Talk 設定・チャット・廃止予定の会話生成）."""

from django.db.models import Sum
from django.urls import reverse
from rest_framework import serializers

from integrations.llm.models import AgentSkill

from .models import ChatMessage, ChatSession, TalkSetting

CHAT_MESSAGE_MAX_LENGTH = 4000
SESSION_TITLE_MAX_LENGTH = 120


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


class ConfigItemSerializer(serializers.Serializer):
    """設定一覧の各アイテムのシリアライザー."""

    name = serializers.CharField(help_text="設定名")
    display_name = serializers.CharField(help_text="表示名")
    tts_enabled = serializers.BooleanField(help_text="TTS有効フラグ")


class ConfigListResponseSerializer(serializers.Serializer):
    """設定一覧レスポンスのシリアライザー."""

    configs = ConfigItemSerializer(many=True, help_text="設定一覧")


class TalkSceneSerializer(serializers.Serializer):
    """シーン（スキル）の名前と説明."""

    name = serializers.CharField(read_only=True, help_text="スキル名")
    description = serializers.CharField(
        read_only=True, help_text="説明（フロントの選択肢に出す）"
    )


class TalkSettingSummarySerializer(serializers.Serializer):
    """セッションの Talk 設定（ID と名前）."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class TalkSettingItemSerializer(serializers.ModelSerializer):
    """Talk 設定の一覧の 1 項目（選べるシーンは `enabled_skills` を先に引いておく）."""

    skills = TalkSceneSerializer(
        many=True,
        read_only=True,
        source="enabled_skills",
        help_text="この設定で選べる有効なシーン（名前順）",
    )

    class Meta:
        model = TalkSetting
        fields = ("id", "name", "tts_enabled", "skills")
        read_only_fields = fields


class TalkSettingListResponseSerializer(serializers.Serializer):
    """Talk 設定の一覧のレスポンス."""

    settings = TalkSettingItemSerializer(
        many=True, help_text="有効な Talk 設定（名前順）"
    )


class _SessionSettingFieldsMixin(serializers.Serializer):
    """セッションの Talk 設定・シーン・音声の有無（Talk 設定がなければ null と false）."""

    setting = TalkSettingSummarySerializer(read_only=True, allow_null=True)
    skill = TalkSceneSerializer(read_only=True, allow_null=True)
    tts_enabled = serializers.SerializerMethodField(
        help_text="応答に音声が付くか（Talk 設定の音声合成）"
    )

    def get_tts_enabled(self, obj: ChatSession) -> bool:
        return obj.setting is not None and obj.setting.tts_enabled


class ChatSessionListItemSerializer(
    _SessionSettingFieldsMixin, serializers.ModelSerializer
):
    """セッション一覧の 1 項目."""

    message_count = serializers.IntegerField(read_only=True)
    total_audio_bytes = serializers.IntegerField(read_only=True)

    class Meta:
        model = ChatSession
        fields = (
            "id",
            "title",
            "setting",
            "skill",
            "tts_enabled",
            "message_count",
            "total_audio_bytes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ChatSessionMessageDetailSerializer(serializers.ModelSerializer):
    """セッション詳細内の各メッセージ."""

    audio_url = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = (
            "id",
            "sequence",
            "role",
            "content",
            "audio_url",
            "audio_format",
            "audio_size_bytes",
            "created_at",
        )
        read_only_fields = fields

    def get_audio_url(self, obj: ChatMessage) -> str | None:
        if not obj.audio_file:
            return None
        request = self.context.get("request")
        path = reverse(
            "talk:session-message-audio",
            kwargs={"session_id": obj.session_id, "msg_id": obj.id},
        )
        if request is not None:
            return request.build_absolute_uri(path)
        return path


class ChatSessionDetailSerializer(
    _SessionSettingFieldsMixin, serializers.ModelSerializer
):
    """セッション詳細."""

    messages = ChatSessionMessageDetailSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()
    total_audio_bytes = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = (
            "id",
            "title",
            "setting",
            "skill",
            "tts_enabled",
            "messages",
            "message_count",
            "total_audio_bytes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_message_count(self, obj: ChatSession) -> int:
        return obj.messages.count()

    def get_total_audio_bytes(self, obj: ChatSession) -> int:
        return obj.messages.aggregate(total=Sum("audio_size_bytes"))["total"] or 0


class ChatTurnDoneSerializer(ChatSessionDetailSerializer):
    """チャットのターン完了時のセッション要約（SSE の done イベント）."""

    class Meta(ChatSessionDetailSerializer.Meta):
        fields = ("title", "message_count", "total_audio_bytes", "updated_at")
        read_only_fields = fields


class ChatSessionCreateSerializer(serializers.Serializer):
    """セッション作成（Talk 設定とシーンを固定する）."""

    setting = serializers.PrimaryKeyRelatedField(
        queryset=TalkSetting.objects.filter(is_enabled=True),
        help_text="使う Talk 設定の ID（有効なもの。作成後固定）",
        error_messages={
            "required": "Talk 設定を選んでください",
            "null": "Talk 設定を選んでください",
            "does_not_exist": "選んだ Talk 設定は見つからないか、無効です",
            "incorrect_type": "Talk 設定は ID で指定してください",
        },
    )
    # 関係のフィールドは空文字を None として扱う（シーンなし）
    skill = serializers.SlugRelatedField(
        slug_field="name",
        queryset=AgentSkill.objects.filter(is_enabled=True),
        required=False,
        allow_null=True,
        help_text=(
            "シーンのスキル名（Talk 設定で選べる有効なもの。なしなら省略か null。"
            "作成後固定）"
        ),
        error_messages={
            "does_not_exist": "選んだシーンは見つからないか、無効です",
            "invalid": "選んだシーンは見つからないか、無効です",
        },
    )

    def validate(self, attrs):
        skill = attrs.get("skill")
        if (
            skill is not None
            and not attrs["setting"].skills.filter(pk=skill.pk).exists()
        ):
            raise serializers.ValidationError(
                {"skill": "このシーンは選んだ Talk 設定では使えません"}
            )
        return attrs


class ChatSessionUpdateSerializer(serializers.ModelSerializer):
    """セッション更新（title のみ）."""

    class Meta:
        model = ChatSession
        fields = ("title",)


class SessionMessageInputSerializer(serializers.Serializer):
    """セッションへの新規メッセージ送信."""

    content = serializers.CharField(
        required=True,
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        trim_whitespace=False,
        allow_blank=False,
        help_text=f"ユーザー発話本文（最大 {CHAT_MESSAGE_MAX_LENGTH} 文字）",
    )


class SessionMessageEditSerializer(serializers.Serializer):
    """既存メッセージの編集再送."""

    content = serializers.CharField(
        required=True,
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        trim_whitespace=False,
        allow_blank=False,
        help_text="編集後の本文（対象 user メッセージ以降は破棄される）",
    )


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
