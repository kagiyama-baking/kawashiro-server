"""
django_apiプロジェクトのURL設定

`urlpatterns`リストはURLをビューにルーティングします。詳細については以下を参照してください:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
例:
関数ビュー
    1. インポートを追加:  from my_app import views
    2. URLをurlpatternsに追加:  path('', views.home, name='home')
クラスベースビュー
    1. インポートを追加:  from other_app.views import Home
    2. URLをurlpatternsに追加:  path('', Home.as_view(), name='home')
他のURLconfをインクルード
    1. include()関数をインポート: from django.urls import include, path
    2. URLをurlpatternsに追加:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView
)

# プロジェクト全体のURLパターン定義
urlpatterns = [
    # Django管理画面のURL
    path('admin/', admin.site.urls),

    # API Documentation (OpenAPI/Swagger)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Swagger UI
    path('api/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # Redoc UI (alternative documentation UI)
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # ユーザー関連APIのURL（user.urlsにルーティング）
    path('api/user/', include('user.urls')),
    # OneDrive関連APIのURL（onedrive.urlsにルーティング）
    path('api/onedrive/', include('onedrive.urls')),
]
