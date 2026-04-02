"""django_apiプロジェクトパッケージ."""

# Djangoの起動時にCeleryアプリを読み込む
from .celery import app as celery_app

__all__ = ("celery_app",)
