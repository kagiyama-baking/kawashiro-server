from django.apps import AppConfig


class TtsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.tts"
    label = "tts"
    verbose_name = "Text-to-Speech"
