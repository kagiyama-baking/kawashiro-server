"""Django admin の表示順カスタマイズのテスト."""

import pytest
from django.contrib import admin
from django.test import RequestFactory

from core.apps import ADMIN_APP_ORDER


@pytest.mark.django_db
def test_admin_app_list_follows_configured_order(superuser):
    """get_app_list が ADMIN_APP_ORDER で並んで返る."""
    req = RequestFactory().get("/admin/")
    req.user = superuser

    app_list = admin.site.get_app_list(req)
    labels = [entry["app_label"] for entry in app_list]
    ordered = [lbl for lbl in labels if lbl in ADMIN_APP_ORDER]

    assert ordered == [lbl for lbl in ADMIN_APP_ORDER if lbl in labels]


@pytest.mark.django_db
def test_celery_beat_label_is_celery(superuser):
    """django-celery-beat の表示名が「Celery」に変更されている."""
    req = RequestFactory().get("/admin/")
    req.user = superuser

    app_list = admin.site.get_app_list(req)
    celery = next(
        (entry for entry in app_list if entry["app_label"] == "django_celery_beat"),
        None,
    )
    assert celery is not None
    assert celery["name"] == "Celery"


@pytest.mark.django_db
def test_renamed_verbose_names_applied(superuser):
    """verbose_name が指定通りに出力される."""
    req = RequestFactory().get("/admin/")
    req.user = superuser

    names = {
        entry["app_label"]: entry["name"] for entry in admin.site.get_app_list(req)
    }
    assert names.get("msgraph_config") == "Microsoft 365"
    assert names.get("langfuse_integration") == "Langfuse"
    assert names.get("hn_agent") == "HackerNews Agent"
    assert names.get("talk") == "Talk Generator"
