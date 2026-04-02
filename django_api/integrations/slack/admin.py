"""Slack通知設定管理画面."""

from django import forms
from django.contrib import admin, messages

from .models import SlackConfig


class SlackConfigForm(forms.ModelForm):
    """SlackConfig用カスタムフォーム."""

    webhook_url = forms.CharField(
        label="Webhook URL",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "https://hooks.slack.com/services/...",
                "autocomplete": "off",
            },
            render_value=False,
        ),
        required=False,
        help_text="Webhook URLを入力してください。空のままにすると既存の値を保持します。",
    )

    class Meta:
        model = SlackConfig
        fields = ["name", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance._encrypted_webhook_url:
            self.fields[
                "webhook_url"
            ].help_text = (
                "Webhook URLは既に設定されています。変更する場合のみ入力してください。"
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        webhook_url = self.cleaned_data.get("webhook_url")
        if webhook_url:
            instance.webhook_url = webhook_url
        if commit:
            instance.save()
        return instance


@admin.register(SlackConfig)
class SlackConfigAdmin(admin.ModelAdmin):
    """Slack通知設定管理画面."""

    form = SlackConfigForm
    list_display = ["name", "is_active", "updated_at"]
    list_filter = ["is_active"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "基本設定",
            {
                "fields": ("name", "is_active"),
                "description": "設定の名前と有効/無効を設定します。",
            },
        ),
        (
            "認証設定",
            {
                "fields": ("webhook_url",),
                "description": "Webhook URLは暗号化されてデータベースに保存されます。",
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
