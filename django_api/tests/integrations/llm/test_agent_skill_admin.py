"""Agent Skills（AgentSkill）の管理画面（一覧・追加・変更）のテスト."""

import pytest
from django.urls import reverse

from integrations.llm.models import AgentSkill
from tests.fixtures.factories import AgentSkillFactory

# 管理画面に出す、本文のプロンプト名の規則（HTML ではエスケープして出す）
ESCAPED_PROMPT_NAME_RULE = "companion-skill-&lt;スキル名&gt;"


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


@pytest.mark.integration
@pytest.mark.django_db
class TestAgentSkillAdmin:
    """Agent Skills の一覧・追加・変更の画面."""

    def test_changelist_shows_prompt_name_and_label_of_skill(self, admin_site_client):
        """一覧に、スキルの本文のプロンプト名とラベルが並ぶ."""
        AgentSkillFactory(name="good-morning", label="staging")

        response = admin_site_client.get(
            reverse("admin:llm_config_agentskill_changelist")
        )

        assert response.status_code == 200
        content = _content(response)
        assert (
            '<td class="field-langfuse_prompt_name">companion-skill-good-morning</td>'
            in content
        )
        assert '<td class="field-label">staging</td>' in content

    def test_change_page_shows_prompt_name_as_read_only(self, admin_site_client):
        """変更画面では、本文のプロンプト名を読み取り専用で出す（名前から決まる）."""
        skill = AgentSkillFactory(name="good-morning")

        response = admin_site_client.get(
            reverse("admin:llm_config_agentskill_change", args=[skill.pk])
        )

        assert response.status_code == 200
        assert '<div class="readonly">companion-skill-good-morning</div>' in (
            _content(response)
        )
        assert "langfuse_prompt_name" not in response.context["adminform"].form.fields

    def test_change_page_renders_description_as_textarea(self, admin_site_client):
        """説明は複数行で書ける."""
        skill = AgentSkillFactory(name="good-morning")

        response = admin_site_client.get(
            reverse("admin:llm_config_agentskill_change", args=[skill.pk])
        )

        assert '<textarea name="description"' in _content(response)

    def test_add_page_shows_prompt_name_rule_as_read_only(self, admin_site_client):
        """追加画面では、名前がまだないので、プロンプト名の規則を出す."""
        response = admin_site_client.get(reverse("admin:llm_config_agentskill_add"))

        assert response.status_code == 200
        assert f'<div class="readonly">{ESCAPED_PROMPT_NAME_RULE}</div>' in (
            _content(response)
        )

    def test_change_page_escapes_prompt_name_rule_in_html(self, admin_site_client):
        """説明文と入力の案内には、規則の山かっこを HTML のまま入れない（エスケープする）."""
        skill = AgentSkillFactory(name="good-morning")

        response = admin_site_client.get(
            reverse("admin:llm_config_agentskill_change", args=[skill.pk])
        )

        content = _content(response)
        assert ESCAPED_PROMPT_NAME_RULE in content
        assert "companion-skill-<" not in content

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
