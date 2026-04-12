"""HN Agent管理画面設定."""

from django.contrib import admin, messages

from .models import (
    HNAgentConfig,
    HNThread,
    HNThreadSnapshot,
)


class HNThreadSnapshotInline(admin.TabularInline):
    """HNスレッドスナップショットのインライン表示."""

    model = HNThreadSnapshot
    extra = 0
    readonly_fields = ("score", "num_comments", "fetched_at")
    ordering = ("-fetched_at",)


@admin.register(HNThread)
class HNThreadAdmin(admin.ModelAdmin):
    """HNスレッド管理."""

    list_display = ("hn_id", "title", "author", "is_investigated", "first_seen")
    list_filter = ("is_investigated",)
    search_fields = ("title", "author", "hn_id")
    readonly_fields = ("first_seen",)
    inlines = [HNThreadSnapshotInline]


@admin.register(HNThreadSnapshot)
class HNThreadSnapshotAdmin(admin.ModelAdmin):
    """HNスナップショット管理."""

    list_display = ("thread", "score", "num_comments", "fetched_at")
    list_filter = ("fetched_at",)
    readonly_fields = ("fetched_at",)


@admin.register(HNAgentConfig)
class HNAgentConfigAdmin(admin.ModelAdmin):
    """HN Agent設定管理."""

    list_display = (
        "name",
        "is_active",
        "score_threshold",
        "velocity_threshold",
        "poll_interval_seconds",
        "updated_at",
    )
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "updated_at")

    autocomplete_fields = (
        "orchestrator_system_prompt",
        "orchestrator_user_prompt",
        "detective_system_prompt",
        "detective_user_prompt",
    )

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "is_active"),
                "description": "設定の名前と有効/無効を設定します。LLMモデルやAPIキーはOpenAI API設定で管理してください。",
            },
        ),
        (
            "LLM設定",
            {
                "fields": ("reasoning_effort",),
                "description": "モデルやAPIキーはLLMサービス設定で管理。ここでは推論深度を設定。",
            },
        ),
        (
            "プロンプト参照（Langfuse）",
            {
                "fields": (
                    "orchestrator_system_prompt",
                    "orchestrator_user_prompt",
                    "detective_system_prompt",
                    "detective_user_prompt",
                ),
                "description": (
                    "Orchestrator / Detective それぞれの system / user プロンプトを "
                    "Langfuseプロンプト参照から選択します。"
                ),
            },
        ),
        (
            "調査トリガー設定",
            {
                "fields": (
                    "score_threshold",
                    "velocity_threshold",
                ),
            },
        ),
        (
            "ポーリング設定",
            {
                "fields": ("poll_interval_seconds", "front_page_limit"),
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

    actions = ["activate_config"]

    @admin.action(description="選択した設定を有効にする")
    def activate_config(self, request, queryset):
        """選択した設定を有効にするアクション."""
        if queryset.count() != 1:
            self.message_user(
                request,
                "有効にする設定は1つだけ選択してください。",
                level=messages.ERROR,
            )
            return
        config = queryset.first()
        config.is_active = True
        config.save()
        self.message_user(request, f"設定「{config.name}」を有効にしました。")
