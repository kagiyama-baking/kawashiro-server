"""Companion の管理画面（設定・Agent Skills・有効化アクション）のテスト."""

import pytest
from django.contrib import messages
from django.contrib.admin.widgets import AutocompleteSelect, FilteredSelectMultiple
from django.contrib.messages import get_messages
from django.urls import reverse

from features.companion.models import AgentSkill, CompanionConfig
from tests.fixtures.factories import (
    AgentSkillFactory,
    CompanionConfigFactory,
    LangfusePromptRefFactory,
)

# 管理画面に出す、本文のプロンプト名の規則（HTML ではエスケープして出す）
ESCAPED_PROMPT_NAME_RULE = "companion-skill-&lt;スキル名&gt;"


@pytest.fixture(autouse=True)
def _static_storage_without_manifest(settings):
    """管理画面のテンプレートを描画できるよう、manifest を使わない保存先にする.

    テストの前に collectstatic はしないので、本番と同じ manifest 付きの保存先では
    テンプレートの `{% static %}` が manifest にない名前で失敗する。
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


@pytest.fixture
def admin_site_client(client, superuser):
    """管理画面にログインしたクライアント."""
    client.force_login(superuser)
    return client


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

    def test_change_page_skills_use_filtered_select_multiple(self, admin_site_client):
        """スキルは、登録済みのスキルから左右の一覧で選ぶ."""
        config = CompanionConfigFactory()

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[config.pk])
        )

        widget = response.context["adminform"].form.fields["skills"].widget.widget
        assert isinstance(widget, FilteredSelectMultiple)

    def test_change_page_skill_choices_show_prompt_name_and_label(
        self, admin_site_client
    ):
        """スキルの選択肢には、スキル名と本文のプロンプト名@ラベルが出る."""
        AgentSkillFactory(name="good-morning", label="staging")
        config = CompanionConfigFactory()

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[config.pk])
        )

        assert "good-morning（companion-skill-good-morning@staging）" in _content(
            response
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


@pytest.mark.integration
@pytest.mark.django_db
class TestAgentSkillAdmin:
    """Agent Skills の一覧・追加・変更の画面."""

    def test_changelist_shows_prompt_name_and_label_of_skill(self, admin_site_client):
        """一覧に、スキルの本文のプロンプト名とラベルが並ぶ."""
        AgentSkillFactory(name="good-morning", label="staging")

        response = admin_site_client.get(
            reverse("admin:companion_agentskill_changelist")
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
            reverse("admin:companion_agentskill_change", args=[skill.pk])
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
            reverse("admin:companion_agentskill_change", args=[skill.pk])
        )

        assert '<textarea name="description"' in _content(response)

    def test_add_page_shows_prompt_name_rule_as_read_only(self, admin_site_client):
        """追加画面では、名前がまだないので、プロンプト名の規則を出す."""
        response = admin_site_client.get(reverse("admin:companion_agentskill_add"))

        assert response.status_code == 200
        assert f'<div class="readonly">{ESCAPED_PROMPT_NAME_RULE}</div>' in (
            _content(response)
        )

    def test_change_page_escapes_prompt_name_rule_in_html(self, admin_site_client):
        """説明文と入力の案内には、規則の山かっこを HTML のまま入れない（エスケープする）."""
        skill = AgentSkillFactory(name="good-morning")

        response = admin_site_client.get(
            reverse("admin:companion_agentskill_change", args=[skill.pk])
        )

        content = _content(response)
        assert ESCAPED_PROMPT_NAME_RULE in content
        assert "companion-skill-<" not in content

    def test_add_with_valid_values_creates_skill(self, admin_site_client):
        """追加画面から、名前・説明・ラベル・有効を入れてスキルを登録できる."""
        response = admin_site_client.post(
            reverse("admin:companion_agentskill_add"), _skill_form_data()
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
            reverse("admin:companion_agentskill_add"), _skill_form_data()
        )

        assert response.status_code == 200
        assert "name" in response.context["adminform"].form.errors
        assert AgentSkill.objects.count() == 1
