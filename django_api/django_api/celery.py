"""Celeryアプリケーション設定."""

import os

from celery import Celery

# Djangoの設定モジュールを指定
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_api.settings")

app = Celery("django_api")

# Django settingsからCELERY_で始まる設定を読み込む
app.config_from_object("django.conf:settings", namespace="CELERY")

# 登録済みDjangoアプリからタスクを自動検出
app.autodiscover_tasks()
