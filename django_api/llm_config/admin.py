"""LLM API設定管理画面"""

from django import forms
from django.contrib import admin, messages

from .models import OpenAIConfig


class BaseLLMConfigForm(forms.ModelForm):
    """LLM設定用の基底カスタムフォーム"""

    # APIキー入力用の非暗号化フィールド
    api_key = forms.CharField(
        label="APIキー",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "sk-...",
                "autocomplete": "off",
            },
            render_value=False,
        ),
        required=False,
        help_text="APIキーを入力してください。空のままにすると既存の値を保持します。",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 既存のAPIキーがある場合はヘルプテキストを変更
        if self.instance.pk and self.instance._encrypted_api_key:
            self.fields[
                "api_key"
            ].help_text = (
                "APIキーは既に設定されています。変更する場合のみ入力してください。"
            )

    def save(self, commit=True):
        instance = super().save(commit=False)

        # APIキーが入力された場合のみ更新
        api_key = self.cleaned_data.get("api_key")
        if api_key:
            try:
                instance.api_key = api_key
            except ValueError as e:
                raise forms.ValidationError(
                    f"APIキーの暗号化に失敗しました: {e}"
                ) from e

        if commit:
            instance.save()
        return instance


class OpenAIConfigForm(BaseLLMConfigForm):
    """OpenAIConfig用のカスタムフォーム"""

    class Meta:
        model = OpenAIConfig
        fields = [
            "name",
            "is_active",
            "model",
            "timeout",
        ]


@admin.register(OpenAIConfig)
class OpenAIConfigAdmin(admin.ModelAdmin):
    """OpenAIConfig管理画面設定"""

    form = OpenAIConfigForm

    list_display = ["name", "is_active", "model", "timeout", "updated_at"]
    list_filter = ["is_active", "model"]
    search_fields = ["name", "model"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "is_active"),
                "description": "設定の名前と有効/無効を設定します。有効にできる設定は1つだけです。",
            },
        ),
        (
            "モデル設定",
            {
                "fields": ("model", "timeout"),
                "description": "使用するOpenAIモデルとタイムアウトを設定します。",
            },
        ),
        (
            "認証設定",
            {
                "fields": ("api_key",),
                "description": "APIキーは暗号化されてデータベースに保存されます。",
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
        """選択した設定を有効にするアクション"""
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

        self.message_user(
            request,
            f"設定「{config.name}」を有効にしました。",
        )
