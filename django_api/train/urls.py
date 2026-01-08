"""URL configuration for train API."""

from django.urls import path

from train import views

app_name = "train"

urlpatterns = [
    path("diainfo/", views.DiainfoView.as_view(), name="diainfo"),
]
