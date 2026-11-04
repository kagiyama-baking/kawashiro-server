"""Agent Skills（AgentSkill）の管理画面（一覧・追加・変更）のテスト."""

import pytest
from django.urls import reverse

from integrations.llm.models import AgentSkill
from tests.fixtures.factories import AgentSkillFactory

# 以前の、本文のプロンプト名の接頭辞（いまはスキル名がそのままプロンプト名なので画面に出さない）
OLD_PROMPT_NAME_PREFIX = "companion-skill-"


def _skill_form_data(**fields) -> dict:
    """Agent Skills の追加フォームの送信内容."""
    return {
        "name": "good-morning",
        "description": "朝のあいさつ（「おはよう」など）",
        "label": "staging",
        "is_enabled": "on",
        **fields,
    }


def _content(response) -> str:
    """画面の HTML."""
    return response.content.decode()


def _page_url(page: str, skill: AgentSkill) -> str:
    """Agent Skills の一覧・追加・変更（skill の）画面の URL."""
    if page == "change":
        return reverse("admin:llm_config_agentskill_change", args=[skill.pk])
    return reverse(f"admin:llm_config_agentskill_{page}")


@pytest.mark.integration
@pytest.mark.django_db
class TestAgentSkillAdmin:
    """Agent Skills の一覧・追加・変更の画面."""

    def test_changelist_shows_label_without_prompt_name_column(self, admin_site_client):
        """一覧には名前・ラベル・有効が並び、本文のプロンプト名の列はない（名前がプロンプト名）."""
        AgentSkillFactory(name="good-morning", label="staging")

        response = admin_site_client.get(
            reverse("admin:llm_config_agentskill_changelist")
        )

        assert response.status_code == 200
        content = _content(response)
        assert '<td class="field-label">staging</td>' in content
        assert "field-langfuse_prompt_name" not in content

    @pytest.mark.parametrize("page", ["changelist", "add", "change"])
    def test_page_never_shows_old_prompt_name_prefix(self, admin_site_client, page):
        """一覧・追加・変更のどの画面にも、以前のプロンプト名の接頭辞（companion-skill-）は出ない."""
        skill = AgentSkillFactory(name="good-morning")

        response = admin_site_client.get(_page_url(page, skill))

        assert response.status_code == 200
        assert OLD_PROMPT_NAME_PREFIX not in _content(response)

    def test_change_page_has_no_read_only_field(self, admin_site_client):
        """変更画面に読み取り専用の欄はない（入力するのは名前・説明・有効・ラベル）."""
        skill = AgentSkillFactory(name="good-morning")

        response = admin_site_client.get(
            reverse("admin:llm_config_agentskill_change", args=[skill.pk])
        )

        adminform = response.context["adminform"]
        assert not adminform.readonly_fields
        assert set(adminform.form.fields) == {
            "name",
            "description",
            "label",
            "is_enabled",
        }

    def test_add_page_explains_body_is_prompt_with_same_name(self, admin_site_client):
        """追加画面の説明に、本文はスキル名と同じ名前の Langfuse の text プロンプトから読むと出す."""
        response = admin_site_client.get(reverse("admin:llm_config_agentskill_add"))

        assert "スキル名と同じ名前の Langfuse の text プロンプト" in _content(response)

    def test_change_page_renders_description_as_textarea(self, admin_site_client):
        """説明は複数行で書ける."""
        skill = AgentSkillFactory(name="good-morning")

        response = admin_site_client.get(
            reverse("admin:llm_config_agentskill_change", args=[skill.pk])
        )

        assert '<textarea name="description"' in _content(response)

    def test_add_with_valid_values_creates_skill(self, admin_site_client):
        """追加画面から、名前・説明・ラベル・有効を入れてスキルを登録できる."""
        response = admin_site_client.post(
            reverse("admin:llm_config_agentskill_add"), _skill_form_data()
        )

        assert response.status_code == 302
        skill = AgentSkill.objects.get()
        assert (skill.name, skill.description, skill.label, skill.is_enabled) == (
            "good-morning",
            "朝のあいさつ（「おはよう」など）",
            "staging",
            True,
        )

    def test_add_with_duplicate_name_shows_error_and_saves_nothing(
        self, admin_site_client
    ):
        """登録済みの名前で追加すると、名前のエラーを表示して保存しない."""
        AgentSkillFactory(name="good-morning")

        response = admin_site_client.post(
            reverse("admin:llm_config_agentskill_add"), _skill_form_data()
        )

        assert response.status_code == 200
        assert "name" in response.context["adminform"].form.errors
        assert AgentSkill.objects.count() == 1
