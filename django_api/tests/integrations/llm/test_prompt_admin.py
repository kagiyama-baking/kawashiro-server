"""Prompts（Prompt）の管理画面と、設定がプロンプトを選ぶ欄（autocomplete）のテスト."""

import pytest
from django.urls import NoReverseMatch, reverse

from integrations.llm.models import Prompt
from tests.fixtures.factories import PromptFactory

# HN Agent 設定がプロンプトを選ぶ 8 本の外部キー
HN_PROMPT_FIELDS = (
    "orchestrator_system_prompt",
    "orchestrator_user_prompt",
    "detective_system_prompt",
    "detective_user_prompt",
    "devils_advocate_system_prompt",
    "devils_advocate_user_prompt",
    "security_responder_system_prompt",
    "security_responder_user_prompt",
)


def _page_url(page: str, prompt: Prompt) -> str:
    """Prompts の一覧・追加・変更（prompt の）画面の URL."""
    if page == "change":
        return reverse("admin:llm_config_prompt_change", args=[prompt.pk])
    return reverse(f"admin:llm_config_prompt_{page}")


@pytest.mark.integration
@pytest.mark.django_db
class TestPromptAdminPages:
    """AI設定 → Prompts の一覧・追加・変更の画面."""

    @pytest.mark.parametrize("page", ["changelist", "add", "change"])
    def test_page_opens(self, admin_site_client, page):
        """一覧・追加・変更の画面を開ける."""
        prompt = PromptFactory(name="companion-system")

        response = admin_site_client.get(_page_url(page, prompt))

        assert response.status_code == 200

    def test_changelist_lists_registered_prompts(self, admin_site_client):
        """一覧に、登録したプロンプトが並ぶ."""
        PromptFactory(name="companion-system")

        response = admin_site_client.get(reverse("admin:llm_config_prompt_changelist"))

        assert "companion-system" in response.content.decode()

    def test_old_langfuse_prompt_ref_admin_is_gone(self):
        """以前の「Langfuse → Langfuseプロンプト参照」の画面はない."""
        with pytest.raises(NoReverseMatch):
            reverse("admin:langfuse_integration_langfusepromptref_changelist")


@pytest.mark.integration
@pytest.mark.django_db
class TestPromptAutocomplete:
    """設定（HN Agent・Companion・Talk）のプロンプトの欄は、Prompts を検索して選ぶ."""

    @pytest.mark.parametrize(
        ("app_label", "model_name", "field_name"),
        [
            *(("hn_agent", "hnagentconfig", field) for field in HN_PROMPT_FIELDS),
            ("companion", "companionconfig", "system_prompt"),
            ("talk", "talksetting", "system_prompt"),
        ],
    )
    def test_autocomplete_returns_prompts_matching_term(
        self, admin_site_client, app_label, model_name, field_name
    ):
        """検索欄に打った語で、名前が合うプロンプトだけが候補に出る."""
        prompt = PromptFactory(name="companion-system")
        PromptFactory(name="talk-system")

        response = admin_site_client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": app_label,
                "model_name": model_name,
                "field_name": field_name,
                "term": "companion",
            },
        )

        assert response.status_code == 200
        assert [result["id"] for result in response.json()["results"]] == [
            str(prompt.pk)
        ]
