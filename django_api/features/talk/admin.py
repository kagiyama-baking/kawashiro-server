"""Talk の管理画面（Talk 設定・チャット履歴）."""

from django.contrib import admin
from django.db.models import Sum

from .models import ChatMessage, ChatSession, TalkSetting


@admin.register(TalkSetting)
class TalkSettingAdmin(admin.ModelAdmin):
    """Talk 設定 Admin."""

    list_display = (
        "name",
        "is_enabled",
        "system_prompt",
        "tts_enabled",
        "updated_at",
    )
    list_filter = ("is_enabled", "tts_enabled")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("system_prompt",)
    filter_horizontal = ("skills",)

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "is_enabled"),
                "description": (
                    "複数の設定を有効にできます。有効な設定を、フロントの Talk で選べます。"
                    "LLM の接続先は「AI設定 → サービス設定」の Talk で管理します。"
                ),
            },
        ),
        (
            "システムプロンプト",
            {
                "fields": ("system_prompt",),
                "description": (
                    "チャットのシステムプロンプト（Langfuse の text プロンプト）を、"
                    "「AI設定 → Prompts」に登録したものから選択します。変数は展開しません。"
                ),
            },
        ),
        (
            "シーン",
            {
                "fields": ("skills",),
                "description": (
                    "Agent Skills に登録したスキルから、この設定で選べるシーンを選びます。"
                    "無効にしたスキルは、ここで選んでいてもフロントでは選べません"
                    "（そのシーンのチャットも続けられません）。チャットでは、選んだシーンの本文を"
                    "システムプロンプトの後ろに足します（ツールは使いません）。"
                ),
            },
        ),
        (
            "音声",
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
            "メタ情報",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
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
        "setting",
        "skill",
        "message_count",
        "total_audio_bytes",
        "updated_at",
    )
    list_filter = (
        ("setting", admin.RelatedOnlyFieldListFilter),
        ("skill", admin.RelatedOnlyFieldListFilter),
        "created_at",
    )
    search_fields = ("title", "user__email")
    list_select_related = ("user", "setting", "skill")
    # Talk 設定・シーンは作成時に固定
    readonly_fields = (
        "id",
        "setting",
        "skill",
        "created_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        """追加するときだけ、Talk 設定とシーンを選べる（作った後は変えない）."""
        if obj is None:
            return ("id", "created_at", "updated_at")
        return self.readonly_fields

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
