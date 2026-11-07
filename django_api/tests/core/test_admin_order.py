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
def test_admin_app_list_companion_follows_hn_agent(superuser):
    """Companion は AI ツール設定の中で HackerNews Agent の直後に並ぶ."""
    req = RequestFactory().get("/admin/")
    req.user = superuser

    labels = [entry["app_label"] for entry in admin.site.get_app_list(req)]

    assert labels.index("companion") == labels.index("hn_agent") + 1


@pytest.mark.integration
@pytest.mark.django_db
def test_admin_app_list_shows_agent_skills_under_llm_config_not_companion(superuser):
    """Agent Skills は AI設定のアプリに出て、Companion には出ない（全エージェントで共有）."""
    req = RequestFactory().get("/admin/")
    req.user = superuser

    models_by_app = {
        entry["app_label"]: [model["object_name"] for model in entry["models"]]
        for entry in admin.site.get_app_list(req)
    }

    assert "AgentSkill" in models_by_app["llm_config"]
    assert "AgentSkill" not in models_by_app["companion"]


@pytest.mark.integration
@pytest.mark.django_db
def test_admin_app_list_shows_prompts_under_llm_config_without_langfuse_group(
    superuser,
):
    """Prompts は AI設定のアプリに出て、Langfuse のグループはない（モデルがない）."""
    req = RequestFactory().get("/admin/")
    req.user = superuser

    models_by_app = {
        entry["app_label"]: [model["object_name"] for model in entry["models"]]
        for entry in admin.site.get_app_list(req)
    }

    assert "Prompt" in models_by_app["llm_config"]
    assert "langfuse_integration" not in models_by_app
    assert "langfuse_integration" not in ADMIN_APP_ORDER


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
    assert names.get("llm_config") == "AI設定"
    assert names.get("hn_agent") == "HackerNews Agent"
    assert names.get("talk") == "Talk"
    assert names.get("companion") == "Companion"
