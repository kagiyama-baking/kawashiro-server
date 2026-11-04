"""Companion の URL 設定."""

from django.urls import path

from .views import CompanionRunView

app_name = "companion"

urlpatterns = [
    path("run/", CompanionRunView.as_view(), name="run"),
]
