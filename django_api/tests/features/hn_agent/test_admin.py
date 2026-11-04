"""HN Agent 設定の管理画面のテスト（モデルと鍵の管理先の案内）."""

import pytest
from django.urls import reverse


@pytest.mark.integration
@pytest.mark.django_db
def test_add_page_points_models_and_keys_to_ai_settings(admin_site_client):
    """モデルと API キーは「AI設定 → LLM設定」で作り、「サービス設定」で割り当てると案内する.

    古い名前（LLMサービス設定・OpenAI API設定）は出さない。
    """
    response = admin_site_client.get(reverse("admin:hn_agent_hnagentconfig_add"))

    assert response.status_code == 200
    content = response.content.decode()
    assert (
        "モデルとAPIキーは「AI設定 → LLM設定」で作り、"
        "「サービス設定」で各サービスに割り当てます" in content
    )
    assert "LLMサービス設定" not in content
    assert "OpenAI API設定" not in content
