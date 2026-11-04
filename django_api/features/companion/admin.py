"""Companion 管理画面設定."""

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from .models import SKILL_PROMPT_NAME_PREFIX, AgentSkill, CompanionConfig

# スキルの本文のプロンプト名の規則（名前がまだない追加画面と、説明文に出す）
_PROMPT_NAME_RULE = f"{SKILL_PROMPT_NAME_PREFIX}<スキル名>"


class AgentSkillForm(forms.ModelForm):
    """スキルの入力フォーム.

    説明はモデルがスキルを選ぶときに読む文なので、複数行で書けるようにする。
    """

    class Meta:
        model = AgentSkill
        fields = ("name", "description", "label", "is_enabled")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


@admin.register(AgentSkill)
class AgentSkillAdmin(admin.ModelAdmin):
    """Agent Skills 管理（Companion 設定は、ここで登録したスキルから使うものを選ぶ）."""

    form = AgentSkillForm
    list_display = ("name", "langfuse_prompt_name", "label", "is_enabled")
    list_filter = ("is_enabled", "label")
    search_fields = ("name", "description")
    readonly_fields = ("langfuse_prompt_name",)

    fieldsets = (
        (
            "スキル",
            {
                "fields": ("name", "langfuse_prompt_name", "description", "is_enabled"),
                # 説明文は HTML として出るので、規則の山かっこはエスケープする
                "description": format_html(
                    "本文は Langfuse の text プロンプト {} から読みます。"
                    "フォールバックはありません。",
                    _PROMPT_NAME_RULE,
                ),
            },
        ),
        (
            "Langfuse",
            {
                "fields": ("label",),
            },
        ),
    )

    @admin.display(description="Langfuse プロンプト名")
    def langfuse_prompt_name(self, obj: AgentSkill | None) -> str:
        """本文のプロンプト名（名前がまだない追加画面では、規則）."""
        if obj is None or not obj.name:
            return _PROMPT_NAME_RULE
        return obj.prompt_name


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
