"""LLM API設定管理画面."""

from django import forms
from django.contrib import admin

from .models import LLMProviderConfig, LLMServiceConfig


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
    """LLMサービス設定管理画面."""

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
