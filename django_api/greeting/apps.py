"""Greeting application configuration."""

from django.apps import AppConfig


class GreetingConfig(AppConfig):
    """Greeting app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "greeting"
