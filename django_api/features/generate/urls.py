"""URL configuration for generate app."""

from django.urls import path

from . import views

app_name = "generate"

urlpatterns = [
    path("generate/", views.GreetingView.as_view(), name="generate"),
    path("today/", views.TodayInfoView.as_view(), name="today"),
    path("configs/", views.ConfigsListView.as_view(), name="configs"),
]
