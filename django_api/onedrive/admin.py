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
            "tenant_id",
            "client_id",
            "cert_thumbprint",
            "target_user",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 既存の秘密鍵がある場合はヘルプテキストを変更
        if self.instance.pk and self.instance._encrypted_private_key:
            self.fields["private_key"].help_text = (
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

    list_display = ["__str__", "tenant_id", "target_user", "updated_at"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
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

    def has_add_permission(self, request):
        """既に設定が存在する場合は追加を禁止"""
        return not MSGraphConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """削除を禁止"""
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """変更画面のカスタマイズ"""
        extra_context = extra_context or {}
        extra_context["show_save_and_add_another"] = False
        extra_context["show_save_and_continue"] = True
        return super().change_view(request, object_id, form_url, extra_context=extra_context)
