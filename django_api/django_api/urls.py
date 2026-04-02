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
    SpectacularSwaggerView,
)

import django_api.admin  # noqa: F401 — django-celery-beat管理画面の日本語化

# プロジェクト全体のURLパターン定義
urlpatterns = [
    # Django管理画面のURL
    path("admin/", admin.site.urls),
    # API Documentation (OpenAPI/Swagger)
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI (メインのドキュメント)
    # url="/api/schema/": nginx経由でアクセスする際、/api プレフィックス付きでスキーマを取得する
    path(
        "swagger/",
        SpectacularSwaggerView.as_view(url="/api/schema/"),
        name="swagger-ui",
    ),
    # Redoc UI (alternative documentation UI)
    path("redoc/", SpectacularRedocView.as_view(url="/api/schema/"), name="redoc"),
    # ユーザー関連APIのURL（user.urlsにルーティング）
    path("user/", include("user.urls")),
    # OneDrive関連APIのURL（onedrive.urlsにルーティング）
    path("onedrive/", include("integrations.onedrive.urls")),
    # メディア処理関連APIのURL（media.urlsにルーティング）
    path("media/", include("features.media.urls")),
    # TTS読み上げ関連APIのURL（tts.urlsにルーティング）
    path("tts/", include("integrations.tts.urls")),
    # Outlook Calendar関連APIのURL（outlook.urlsにルーティング）
    path("outlook/", include("integrations.outlook.urls")),
    # 気象庁天気予報関連APIのURL（weather.urlsにルーティング）
    path("weather/", include("integrations.weather.urls")),
    # 会話生成関連APIのURL
    path("talk/", include("features.talk.urls")),
    # ヘルスチェックURL（認証不要）
    path("health/", include("health.urls")),
    # HN Agent API
    path("hn-agent/", include("features.hn_agent.urls")),
]
