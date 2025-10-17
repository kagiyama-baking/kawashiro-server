from django.urls import path

from user import views


# アプリケーション名の定義
app_name = 'user'

# ユーザー関連のURLパターン定義
urlpatterns = [
      # ユーザー作成エンドポイント
      path('create/', views.CreateUserView.as_view(), name='create'),
      # トークン認証エンドポイント（ログイン）
      path('token/', views.CreateTokenView.as_view(), name='token'),
]
