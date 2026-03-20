from django.urls import path

from . import views

app_name = "tts"

urlpatterns = [
    path("health/", views.TTSHealthView.as_view(), name="health"),
    path("models/", views.TTSModelsView.as_view(), name="models"),
    path(
        "models/<str:model_name>/styles/",
        views.TTSModelStylesView.as_view(),
        name="model-styles",
    ),
    path("synthesize/", views.TTSSynthesizeView.as_view(), name="synthesize"),
]
