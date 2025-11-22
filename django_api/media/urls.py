"""mediaアプリケーションのURLパターン"""
from django.urls import path
from media import views

# アプリケーション名の定義
app_name = 'media'

# メディア処理関連のURLパターン定義
urlpatterns = [
    # ZIP→PDF変換エンドポイント
    path('zip2pdf/', views.Zip2PdfView.as_view(), name='zip2pdf'),
]
