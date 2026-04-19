"""会話生成設定 admin"""

from django.contrib import admin

from .models import TalkConfig


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
