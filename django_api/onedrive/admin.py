"""OneDrive管理画面設定"""

from django import forms
from django.contrib import admin

from .models import MSGraphConfig


class MSGraphConfigForm(forms.ModelForm):
    """MSGraphConfig用のカスタムフォーム"""

    # 秘密鍵入力用の非暗号化フィールド
    private_key = forms.CharField(
        label="秘密鍵",
        widget=forms.Textarea(
            attrs={
                "rows": 10,
                "cols": 80,
                "placeholder": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
            }
        ),
        required=False,
        help_text="PEM形式の秘密鍵を入力してください。空のままにすると既存の値を保持します。",
    )

    class Meta:
        model = MSGraphConfig
        fields = [
            "name",
            "is_active",
            "tenant_id",
            "client_id",
            "cert_thumbprint",
            "target_user",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 既存の秘密鍵がある場合はヘルプテキストを変更
        if self.instance.pk and self.instance._encrypted_private_key:
            self.fields[
                "private_key"
            ].help_text = (
                "秘密鍵は既に設定されています。変更する場合のみ入力してください。"
            )

    def save(self, commit=True):
        instance = super().save(commit=False)

        # 秘密鍵が入力された場合のみ更新
        private_key = self.cleaned_data.get("private_key")
        if private_key:
            instance.private_key = private_key

        if commit:
            instance.save()
        return instance


@admin.register(MSGraphConfig)
class MSGraphConfigAdmin(admin.ModelAdmin):
    """MSGraphConfig管理画面設定"""

    form = MSGraphConfigForm

    list_display = ["name", "is_active", "tenant_id", "target_user", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "tenant_id", "target_user"]
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
            "Azure AD設定",
            {
                "fields": ("tenant_id", "client_id", "cert_thumbprint"),
                "description": "Azure ADアプリケーションの認証情報を設定します。",
            },
        ),
        (
            "認証設定",
            {
                "fields": ("private_key",),
                "description": "秘密鍵は暗号化されてデータベースに保存されます。",
            },
        ),
        (
            "対象設定",
            {
                "fields": ("target_user",),
                "description": "OneDriveにアクセスする対象ユーザーを設定します。",
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
                level="error",
            )
            return

        config = queryset.first()
        config.is_active = True
        config.save()

        self.message_user(
            request,
            f"設定「{config.name}」を有効にしました。",
        )
