"""URL configuration for greeting app."""

from django.urls import path

from . import views

app_name = "greeting"

urlpatterns = [
    path("morning/", views.MorningGreetingView.as_view(), name="morning"),
    path("evening/", views.EveningGreetingView.as_view(), name="evening"),
    path("welcome-home/", views.WelcomeHomeGreetingView.as_view(), name="welcome-home"),
    path("today/", views.TodayInfoView.as_view(), name="today"),
]
