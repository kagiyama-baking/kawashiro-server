"""朝のあいさつ設定 admin"""

from django.contrib import admin

from .models import MorningGreetingConfig


@admin.register(MorningGreetingConfig)
class MorningGreetingConfigAdmin(admin.ModelAdmin):
    """朝のあいさつ設定 Admin"""

    list_display = ("__str__", "area_code", "rail_ids", "tts_enabled")

    fieldsets = (
        (
            None,
            {
                "fields": ("area_code", "rail_ids"),
            },
        ),
        (
            "TTS設定",
            {
                "classes": ("collapse",),
                "fields": (
                    "tts_enabled",
                    "tts_model",
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
            "プロンプト設定",
            {
                "fields": ("system_prompt", "user_prompt"),
            },
        ),
    )

    def has_add_permission(self, request):
        """既に設定が存在する場合は追加不可."""
        if MorningGreetingConfig.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        """削除不可."""
        return False
