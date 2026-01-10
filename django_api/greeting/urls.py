"""URL configuration for greeting app."""

from django.urls import path

from . import views

app_name = "greeting"

urlpatterns = [
    path("morning/", views.MorningGreetingView.as_view(), name="morning"),
    path("today/", views.TodayInfoView.as_view(), name="today"),
]
