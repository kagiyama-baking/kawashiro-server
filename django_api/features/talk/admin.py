"""会話生成設定 admin"""

from django.contrib import admin
from django.db.models import Sum

from .models import ChatMessage, ChatSession, TalkConfig


@admin.register(TalkConfig)
class TalkConfigAdmin(admin.ModelAdmin):
    """会話生成設定 Admin"""

    list_display = (
        "name",
        "display_name",
        "tts_enabled",
    )
    list_filter = ("tts_enabled",)
    search_fields = ("name", "display_name")
    autocomplete_fields = ("system_prompt_ref", "user_prompt_ref")

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "display_name"),
            },
        ),
        (
            "天気設定",
            {
                "fields": ("area_code",),
                "classes": ("collapse",),
                "description": (
                    "プロンプトに `{{weather}}` を含める場合は予報区コードが必須"
                ),
            },
        ),
        (
            "TTS設定",
            {
                "classes": ("collapse",),
                "fields": (
                    "tts_enabled",
                    "tts_model",
                    "tts_format",
                    "tts_style",
                    "tts_style_weight",
                    "tts_speed",
                    "tts_sdp_ratio",
                    "tts_noise_scale",
                    "tts_noise_scale_w",
                ),
            },
        ),
        (
            "プロンプト参照（Langfuse）",
            {
                "fields": ("system_prompt_ref", "user_prompt_ref"),
                "description": (
                    "システムプロンプト・ユーザープロンプトの Langfuse 参照を選択。"
                    "`{{weather}}` `{{events}}` `{{datetime}}` をテンプレートに含めると"
                    "自動的に対応するデータが取得されます。"
                ),
            },
        ),
    )


class ChatMessageInline(admin.TabularInline):
    """ChatSession 内のメッセージインライン表示."""

    model = ChatMessage
    extra = 0
    readonly_fields = (
        "sequence",
        "role",
        "content",
        "audio_format",
        "audio_size_bytes",
        "created_at",
    )
    fields = readonly_fields
    can_delete = True
    show_change_link = False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    """チャットセッション Admin."""

    list_display = (
        "id",
        "user",
        "title",
        "config_name",
        "message_count",
        "total_audio_bytes",
        "updated_at",
    )
    list_filter = ("config_name", "created_at")
    search_fields = ("title", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (ChatMessageInline,)

    @admin.display(description="メッセージ数")
    def message_count(self, obj: ChatSession) -> int:
        return obj.messages.count()

    @admin.display(description="音声合計 (bytes)")
    def total_audio_bytes(self, obj: ChatSession) -> int:
        return obj.messages.aggregate(total=Sum("audio_size_bytes"))["total"] or 0


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """チャットメッセージ Admin."""

    list_display = (
        "session",
        "sequence",
        "role",
        "audio_format",
        "audio_size_bytes",
        "created_at",
    )
    list_filter = ("role", "audio_format")
    search_fields = ("content", "session__title")
    readonly_fields = ("created_at",)
