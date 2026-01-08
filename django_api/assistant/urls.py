"""アシスタントAPIのURLルーティング."""

from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("greeting/", views.GreetingView.as_view(), name="greeting"),
    path("greeting/audio/", views.GreetingAudioView.as_view(), name="greeting-audio"),
    path("chat/", views.ChatView.as_view(), name="chat"),
    path("daily-summary/", views.DailySummaryView.as_view(), name="daily-summary"),
]
