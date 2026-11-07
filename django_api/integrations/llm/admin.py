"""AI設定（LLM設定・サービス設定・Prompts・Agent Skills）の管理画面."""

from django import forms
from django.contrib import admin

from .models import AgentSkill, LLMProviderConfig, LLMServiceConfig, Prompt


class LLMProviderConfigForm(forms.ModelForm):
    """LLMProviderConfig用のカスタムフォーム."""

    proxy_api_key = forms.CharField(
        label="Virtual Key",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "sk-...",
                "autocomplete": "off",
            },
            render_value=False,
        ),
        required=False,
        help_text="LiteLLM Virtual Keyを入力してください。空のままにすると環境変数LITELLM_MASTER_KEYを使用します。",
    )

    class Meta:
        model = LLMProviderConfig
        fields = ["name", "model_alias"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance._encrypted_proxy_api_key:
            self.fields[
                "proxy_api_key"
            ].help_text = (
                "Virtual Keyは既に設定されています。変更する場合のみ入力してください。"
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        proxy_api_key = self.cleaned_data.get("proxy_api_key")
        if proxy_api_key:
            instance.proxy_api_key = proxy_api_key
        if commit:
            instance.save()
        return instance


@admin.register(LLMProviderConfig)
class LLMProviderConfigAdmin(admin.ModelAdmin):
    """LLM設定管理画面."""

    form = LLMProviderConfigForm

    list_display = [
        "name",
        "model_alias",
        "has_virtual_key",
        "updated_at",
    ]
    search_fields = ["name", "model_alias"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "model_alias"),
                "description": "設定名とLiteLLM Proxyのモデルエイリアスを設定します。",
            },
        ),
        (
            "認証設定",
            {
                "fields": ("proxy_api_key",),
                "description": (
                    "LiteLLM Virtual Keyを設定します。"
                    "マスターキーではなくサービス専用のVirtual Keyを使うことで、"
                    "コスト上限の設定やアクセスログの識別が可能になります。"
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

    @admin.display(boolean=True, description="Virtual Key")
    def has_virtual_key(self, obj):
        """Virtual Keyが設定されているかを表示."""
        return bool(obj._encrypted_proxy_api_key)


@admin.register(LLMServiceConfig)
class LLMServiceConfigAdmin(admin.ModelAdmin):
    """サービス設定管理画面（サービスごとに使う LLM設定を割り当てる）."""

    list_display = [
        "service_name",
        "provider_config",
        "is_active",
        "timeout",
    ]
    list_filter = ["is_active"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("service_name", "provider_config", "is_active"),
                "description": "サービスごとに使用するLLM設定を選択します。",
            },
        ),
        (
            "詳細設定",
            {
                "fields": ("timeout",),
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


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    """Prompts 管理（各機能の設定は、ここで登録したプロンプトから選ぶ）."""

    list_display = (
        "name",
        "langfuse_prompt_name",
        "label",
        "description",
        "updated_at",
    )
    list_filter = ("label",)
    # 各機能の設定のプロンプトの欄（autocomplete）が、この検索で候補を出す
    search_fields = ("name", "langfuse_prompt_name", "description")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "description"),
                "description": (
                    "Django 側で一意に識別する名前と用途説明。"
                    "各機能設定（HN Agent / Companion / Talk）はここで登録したプロンプトを"
                    "選択します。"
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
    """Agent Skills 管理（各エージェントの設定は、ここで登録したスキルから使うものを選ぶ）."""

    form = AgentSkillForm
    list_display = ("name", "label", "is_enabled")
    list_filter = ("is_enabled", "label")
    search_fields = ("name", "description")

    fieldsets = (
        (
            "スキル",
            {
                "fields": ("name", "description", "is_enabled"),
                "description": (
                    "本文は、スキル名と同じ名前の Langfuse の text プロンプトを、"
                    "下のラベルで読みます。フォールバックはありません。"
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
