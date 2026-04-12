"""Langfuseプロンプト参照管理画面."""

from django.contrib import admin

from .models import LangfusePromptRef


@admin.register(LangfusePromptRef)
class LangfusePromptRefAdmin(admin.ModelAdmin):
    """Langfuseプロンプト参照 Admin."""

    list_display = (
        "name",
        "langfuse_prompt_name",
        "label",
        "description",
        "updated_at",
    )
    list_filter = ("label",)
    search_fields = ("name", "langfuse_prompt_name", "description")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "description"),
                "description": (
                    "Django 側で一意に識別する名前と用途説明。"
                    "各機能設定（HN Agent / Talk など）はここで登録した参照を選択します。"
                ),
            },
        ),
        (
            "Langfuse連携",
            {
                "fields": ("langfuse_prompt_name", "label"),
                "description": (
                    "Langfuse 上のプロンプト名とラベル。"
                    "Langfuse 接続時はここで指定したプロンプトが取得されます。"
                ),
            },
        ),
        (
            "フォールバック",
            {
                "fields": ("fallback_text",),
                "description": (
                    "Langfuse 接続失敗・プロンプト未登録時に使用されるテキスト。"
                    "`{{変数}}` は呼び出し側の variables で簡易置換されます。"
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
