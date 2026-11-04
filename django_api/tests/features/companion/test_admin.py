"""Companion の管理画面（設定・有効化アクション）のテスト.

Agent Skills の画面は tests/integrations/llm/test_agent_skill_admin.py。
"""

import pytest
from django.contrib import messages
from django.contrib.admin.widgets import AutocompleteSelect, FilteredSelectMultiple
from django.contrib.messages import get_messages
from django.urls import reverse

from features.companion.models import CompanionConfig
from tests.fixtures.factories import (
    AgentSkillFactory,
    CompanionConfigFactory,
    LangfusePromptRefFactory,
)


def _config_form_data(system_prompt_ref, **fields) -> dict:
    """設定の追加フォームの送信内容（スキルは選ばない。TTS は既定値）."""
    return {
        "name": "main",
        "system_prompt_ref": system_prompt_ref.pk,
        "area_code": "130010",
        "rate_limit": 10,
        "tts_model": "",
        "tts_format": "wav",
        "tts_style": "Neutral",
        "tts_style_weight": 1.0,
        "tts_speed": 1.0,
        "tts_sdp_ratio": 0.2,
        "tts_noise_scale": 0.6,
        "tts_noise_scale_w": 0.8,
        **fields,
    }


def _content(response) -> str:
    """画面の HTML."""
    return response.content.decode()


def _activate(admin_site_client, configs):
    """一覧の「選択した設定を有効にする」を実行する."""
    return admin_site_client.post(
        reverse("admin:companion_companionconfig_changelist"),
        {"action": "activate_config", "_selected_action": [c.pk for c in configs]},
    )


def _messages(response) -> list[tuple[int, str]]:
    """管理画面が出したメッセージ（レベルと文）."""
    return [(m.level, m.message) for m in get_messages(response.wsgi_request)]


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionConfigAdminPages:
    """一覧・追加・変更の画面."""

    def test_changelist_for_superuser_lists_configs(self, admin_site_client):
        """一覧に設定が並ぶ."""
        CompanionConfigFactory(name="main")

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_changelist")
        )

        assert response.status_code == 200
        assert "main" in response.content.decode()

    def test_add_page_for_superuser_has_no_skill_inline(self, admin_site_client):
        """追加画面にスキルのインラインはない（スキルは Agent Skills で登録する）."""
        response = admin_site_client.get(reverse("admin:companion_companionconfig_add"))

        assert response.status_code == 200
        assert response.context["inline_admin_formsets"] == []
        assert 'name="skills-TOTAL_FORMS"' not in _content(response)

    def test_add_page_points_llm_connection_to_service_settings(
        self, admin_site_client
    ):
        """基本設定の説明で、LLM の接続先は「AI設定 → サービス設定」で管理すると案内する."""
        response = admin_site_client.get(reverse("admin:companion_companionconfig_add"))

        content = _content(response)
        assert "「AI設定 → サービス設定」の Companion で管理します" in content
        assert "LLMサービス設定" not in content

    def test_change_page_skills_use_filtered_select_multiple(self, admin_site_client):
        """スキルは、登録済みのスキルから左右の一覧で選ぶ."""
        config = CompanionConfigFactory()

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[config.pk])
        )

        widget = response.context["adminform"].form.fields["skills"].widget.widget
        assert isinstance(widget, FilteredSelectMultiple)

    def test_change_page_skill_choices_show_name_and_label(self, admin_site_client):
        """スキルの選択肢は「スキル名@ラベル」（本文を読むプロンプトとその版）."""
        skill = AgentSkillFactory(name="good-morning", label="staging")
        config = CompanionConfigFactory()

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[config.pk])
        )

        assert f'<option value="{skill.pk}">good-morning@staging</option>' in (
            _content(response)
        )

    def test_change_page_system_prompt_ref_uses_autocomplete(self, admin_site_client):
        """システムプロンプトの参照は検索して選ぶ."""
        config = CompanionConfigFactory()

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[config.pk])
        )

        config_fields = response.context["adminform"].form.fields
        assert isinstance(
            config_fields["system_prompt_ref"].widget.widget, AutocompleteSelect
        )

    def test_change_page_shows_system_prompt_section_with_same_label(
        self, admin_site_client
    ):
        """「システムプロンプト」の節に、同じ名前の項目（参照）だけがある."""
        config = CompanionConfigFactory()

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[config.pk])
        )

        adminform = response.context["adminform"]
        sections = {name: options["fields"] for name, options in adminform.fieldsets}
        assert sections["システムプロンプト"] == ("system_prompt_ref",)
        assert adminform.form.fields["system_prompt_ref"].label == "システムプロンプト"

    def test_change_page_shows_skills_section_with_same_label(self, admin_site_client):
        """「スキル」の節に、同じ名前の項目（選ぶスキル）だけがある."""
        config = CompanionConfigFactory()

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[config.pk])
        )

        adminform = response.context["adminform"]
        sections = {name: options["fields"] for name, options in adminform.fieldsets}
        assert sections["スキル"] == ("skills",)
        assert adminform.form.fields["skills"].label == "スキル"

    def test_autocomplete_for_system_prompt_ref_returns_matching_refs(
        self, admin_site_client
    ):
        """参照の検索欄に打った語で、名前が合う参照だけが候補に出る."""
        ref = LangfusePromptRefFactory(name="companion-system")
        LangfusePromptRefFactory(name="talk-system")

        response = admin_site_client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": "companion",
                "model_name": "companionconfig",
                "field_name": "system_prompt_ref",
                "term": "companion",
            },
        )

        assert response.status_code == 200
        assert [result["id"] for result in response.json()["results"]] == [str(ref.pk)]


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionConfigAdminSave:
    """設定を保存する（スキルは登録済みのものから選ぶ）."""

    def test_add_with_selected_skills_creates_config_selecting_them(
        self, admin_site_client
    ):
        """追加画面で選んだスキルだけを、その設定で選んだ状態で保存する."""
        system_prompt = LangfusePromptRefFactory(name="companion-system")
        morning = AgentSkillFactory(name="good-morning")
        night = AgentSkillFactory(name="good-night")
        AgentSkillFactory(name="welcome-home")

        response = admin_site_client.post(
            reverse("admin:companion_companionconfig_add"),
            _config_form_data(system_prompt, skills=[morning.pk, night.pk]),
        )

        assert response.status_code == 302
        config = CompanionConfig.objects.get(name="main")
        assert config.system_prompt_ref == system_prompt
        assert list(config.skills.all()) == [morning, night]

    def test_add_without_skills_creates_config_with_no_skills(self, admin_site_client):
        """スキルを 1 つも選ばなくても保存できる."""
        system_prompt = LangfusePromptRefFactory(name="companion-system")

        response = admin_site_client.post(
            reverse("admin:companion_companionconfig_add"),
            _config_form_data(system_prompt),
        )

        assert response.status_code == 302
        assert not CompanionConfig.objects.get(name="main").skills.exists()


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionConfigActivateAction:
    """一覧の「選択した設定を有効にする」."""

    def test_activate_config_with_one_selected_activates_only_it(
        self, admin_site_client
    ):
        """1 件選ぶと、それを有効にしてほかを無効にする."""
        current = CompanionConfigFactory(name="current", is_active=True)
        target = CompanionConfigFactory(name="next")

        response = _activate(admin_site_client, [target])

        current.refresh_from_db()
        target.refresh_from_db()
        assert current.is_active is False
        assert target.is_active is True
        assert _messages(response) == [
            (messages.INFO, "設定「next」を有効にしました。")
        ]

    def test_activate_config_with_two_selected_shows_error_and_changes_nothing(
        self, admin_site_client
    ):
        """2 件選ぶとエラーを表示し、どれも有効にしない."""
        first = CompanionConfigFactory(name="first")
        second = CompanionConfigFactory(name="second")

        response = _activate(admin_site_client, [first, second])

        assert not CompanionConfig.objects.filter(is_active=True).exists()
        assert _messages(response) == [
            (messages.ERROR, "有効にする設定は1つだけ選択してください。")
        ]
