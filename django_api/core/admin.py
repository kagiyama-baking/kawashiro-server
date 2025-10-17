from core import models
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext as _


class UserAdmin(BaseUserAdmin):
    """カスタムユーザーモデル用の管理画面設定"""

    # リスト表示の並び順（IDで昇順）
    ordering = ['id']
    # 一覧画面に表示するフィールド
    list_display = ['email', 'name']
    # 詳細画面のフィールドセット定義
    fieldsets = (
        # 基本情報セクション（メールアドレスとパスワード）
        (None, {'fields': ('email', 'password')}),
        # 個人情報セクション（名前）
        (_('Personal Info'), {'fields': ('name',)}),
        # 権限セクション（アクティブ状態、スタッフ権限、スーパーユーザー権限）
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        # 重要な日付セクション（最終ログイン日時）
        (_('Important dates'), {'fields': ('last_login',)}),
    )
    # 新規ユーザー作成画面のフィールドセット定義
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2'),
        }),
    )
    # 検索フィールド
    search_fields = ('email', 'name')
    # フィルターサイドバーに表示するフィールド
    filter_horizontal = ()


# カスタムUserモデルを管理画面に登録
admin.site.register(models.User, UserAdmin)
