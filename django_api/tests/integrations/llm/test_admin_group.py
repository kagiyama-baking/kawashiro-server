"""管理画面の「AI設定」グループ（llm_config アプリ）のテスト."""

import pytest
from django.urls import reverse


@pytest.mark.integration
@pytest.mark.django_db
def test_admin_index_shows_ai_settings_group_with_skills_llm_and_service_settings(
    admin_site_client,
):
    """管理画面のトップに「AI設定」が出て、Agent Skills・LLM設定・サービス設定が並ぶ."""
    response = admin_site_client.get(reverse("admin:index"))

    assert response.status_code == 200
    apps = {app["app_label"]: app for app in response.context["app_list"]}
    group = apps["llm_config"]
    assert group["name"] == "AI設定"
    assert [model["name"] for model in group["models"]] == [
        "Agent Skills",
        "LLM設定",
        "サービス設定",
    ]
