"""Companion 管理画面設定（スキルの登録は integrations/llm/admin.py の Agent Skills）."""

from django.contrib import admin, messages

from .models import CompanionConfig


@admin.register(CompanionConfig)
class CompanionConfigAdmin(admin.ModelAdmin):
    """Companion 設定管理."""

    list_display = (
        "name",
        "is_active",
        "system_prompt_ref",
        "area_code",
        "rate_limit",
        "tts_enabled",
        "updated_at",
    )
    list_filter = ("is_active", "tts_enabled")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("system_prompt_ref",)
    filter_horizontal = ("skills",)

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "is_active"),
                "description": (
                    "有効にできるのは 1 つの設定だけです。"
                    "LLM の接続先は「LLMサービス設定」の Companion で管理します。"
                ),
            },
        ),
        (
            "システムプロンプト",
            {
                "fields": ("system_prompt_ref",),
                "description": (
                    "全スキルに共通のシステムプロンプト（Langfuse の text プロンプト）を"
                    "Langfuseプロンプト参照から選択します。"
                ),
            },
        ),
        (
            "スキル",
            {
                "fields": ("skills",),
                "description": (
                    "Agent Skills に登録したスキルから、この設定で使うものを選びます。"
                    "無効にしたスキルは選んでいても使いません。"
                ),
            },
        ),
        (
            "天気",
            {
                "fields": ("area_code",),
            },
        ),
        (
            "回数制限",
            {
                "fields": ("rate_limit",),
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
