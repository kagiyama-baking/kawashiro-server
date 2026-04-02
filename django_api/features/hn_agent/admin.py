"""HN Agent管理画面設定."""

from django.contrib import admin, messages

from .models import (
    HNAgentConfig,
    HNThread,
    HNThreadSnapshot,
    Investigation,
    ThreadEmbedding,
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


@admin.register(Investigation)
class InvestigationAdmin(admin.ModelAdmin):
    """調査結果管理."""

    list_display = ("thread", "agent_type", "created_at")
    list_filter = ("agent_type", "created_at")
    readonly_fields = ("created_at",)


@admin.register(ThreadEmbedding)
class ThreadEmbeddingAdmin(admin.ModelAdmin):
    """スレッド埋め込み管理."""

    list_display = ("thread", "created_at")
    readonly_fields = ("created_at",)


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

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "is_active"),
                "description": "設定の名前と有効/無効を設定します。LLMモデルやAPIキーはOpenAI API設定で管理してください。",
            },
        ),
        (
            "Embedding設定",
            {
                "fields": ("embedding_dimensions",),
                "description": "EmbeddingモデルはOpenAI API設定で管理。ここでは出力次元数のみ設定。",
            },
        ),
        (
            "調査トリガー設定",
            {
                "fields": (
                    "score_threshold",
                    "velocity_threshold",
                    "similarity_threshold",
                ),
            },
        ),
        (
            "ポーリング設定",
            {
                "fields": ("poll_interval_seconds",),
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
