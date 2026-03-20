"""URL configuration for weather app."""

from django.urls import path

from . import views

app_name = "weather"

urlpatterns = [
    path("forecast/", views.WeatherForecastView.as_view(), name="forecast"),
]
