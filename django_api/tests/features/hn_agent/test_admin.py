"""HN Agent 設定の管理画面のテスト（モデルと鍵の管理先の案内）."""

import pytest
from django.urls import reverse


@pytest.mark.integration
@pytest.mark.django_db
def test_add_page_points_models_and_keys_to_ai_settings(admin_site_client):
    """モデルと API キーの管理先は「AI設定 → サービス設定」と案内し、古い名前は出さない."""
    response = admin_site_client.get(reverse("admin:hn_agent_hnagentconfig_add"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "「AI設定 → サービス設定」" in content
    assert "LLMサービス設定" not in content
    assert "OpenAI API設定" not in content
