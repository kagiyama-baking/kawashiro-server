"""Outlookアプリケーションのルーティング設定"""

from django.urls import path

from .views import OutlookEventsView

# URL設定
urlpatterns = [
    # 予定一覧取得
    path("events/", OutlookEventsView.as_view(), name="outlook-events"),
]
