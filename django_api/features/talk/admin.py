"""会話生成設定 admin"""

from django.contrib import admin

from .models import TalkConfig


@admin.register(TalkConfig)
class TalkConfigAdmin(admin.ModelAdmin):
    """会話生成設定 Admin"""

    list_display = (
        "name",
        "display_name",
        "use_weather",
        "use_events",
        "use_datetime",
        "tts_enabled",
    )
    list_filter = ("use_weather", "use_events", "use_datetime", "tts_enabled")
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
            "プレースホルダー設定",
            {
                "fields": ("use_weather", "use_events", "use_datetime"),
                "description": (
                    "有効にしたプレースホルダーが Langfuse プロンプトテンプレートで使用可能になります。"
                ),
            },
        ),
        (
            "天気設定",
            {
                "fields": ("area_code",),
                "classes": ("collapse",),
                "description": "「天気情報を使用」が有効な場合に必須",
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
                    "`{{weather}}` `{{events}}` `{{datetime}}` はテンプレート側で使用可能です。"
                ),
            },
        ),
    )
