"""URL configuration for greeting app."""

from django.urls import path

from . import views

app_name = "greeting"

urlpatterns = [
    path("generate/", views.GreetingView.as_view(), name="generate"),
    path("today/", views.TodayInfoView.as_view(), name="today"),
]
