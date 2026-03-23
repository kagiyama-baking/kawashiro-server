"""会話生成URL設定."""

from django.urls import path

from . import views

app_name = "talk"

urlpatterns = [
    path("synthesize/", views.TalkSynthesizeView.as_view(), name="synthesize"),
    path("datetime/", views.TodayInfoView.as_view(), name="datetime"),
    path("configs/", views.ConfigsListView.as_view(), name="configs"),
]
