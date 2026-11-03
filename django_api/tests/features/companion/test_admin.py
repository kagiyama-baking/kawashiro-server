"""Companion の管理画面（設定 + スキルのインライン + 有効化アクション）のテスト."""

import pytest
from django import forms
from django.contrib import messages
from django.contrib.admin.widgets import AutocompleteSelect
from django.contrib.messages import get_messages
from django.urls import reverse

from features.companion.models import CompanionConfig
from tests.fixtures.factories import (
    CompanionConfigFactory,
    CompanionSkillFactory,
    LangfusePromptRefFactory,
)


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


def _config_form_data(persona_prompt_ref, **fields) -> dict:
    """設定の追加フォームの送信内容（スキルなし。TTS は既定値）."""
    return {
        "name": "main",
        "persona_prompt_ref": persona_prompt_ref.pk,
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
        "skills-TOTAL_FORMS": 0,
        "skills-INITIAL_FORMS": 0,
        "skills-MIN_NUM_FORMS": 0,
        "skills-MAX_NUM_FORMS": 1000,
        **fields,
    }


def _skill_form_data(index: int, name: str, prompt_ref) -> dict:
    """スキルのインラインの 1 行分の送信内容."""
    return {
        f"skills-{index}-name": name,
        f"skills-{index}-description": f"{name} のときに使う",
        f"skills-{index}-prompt_ref": prompt_ref.pk,
        f"skills-{index}-is_enabled": "on",
    }


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

    def test_add_page_for_superuser_renders_skill_inline(self, admin_site_client):
        """追加画面にスキルのインラインがある."""
        response = admin_site_client.get(reverse("admin:companion_companionconfig_add"))

        assert response.status_code == 200
        assert 'name="skills-TOTAL_FORMS"' in response.content.decode()

    def test_change_page_with_skill_renders_description_as_textarea(
        self, admin_site_client
    ):
        """変更画面に登録済みのスキルがあり、説明は複数行で書ける."""
        skill = CompanionSkillFactory(name="good-morning")

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[skill.config.pk])
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert 'value="good-morning"' in content
        assert '<textarea name="skills-0-description"' in content

    def test_change_page_prompt_refs_use_autocomplete(self, admin_site_client):
        """キャラクター設定とスキル本文の参照は検索して選ぶ."""
        skill = CompanionSkillFactory()

        response = admin_site_client.get(
            reverse("admin:companion_companionconfig_change", args=[skill.config.pk])
        )

        config_fields = response.context["adminform"].form.fields
        skill_fields = response.context["inline_admin_formsets"][
            0
        ].formset.form.base_fields
        assert isinstance(
            config_fields["persona_prompt_ref"].widget.widget, AutocompleteSelect
        )
        assert isinstance(skill_fields["prompt_ref"].widget.widget, AutocompleteSelect)
        assert isinstance(skill_fields["description"].widget, forms.Textarea)

    @pytest.mark.parametrize(
        ("model_name", "field_name"),
        [
            pytest.param("companionconfig", "persona_prompt_ref", id="persona"),
            pytest.param("companionskill", "prompt_ref", id="skill_body"),
        ],
    )
    def test_autocomplete_for_prompt_ref_field_returns_matching_refs(
        self, admin_site_client, model_name, field_name
    ):
        """参照の検索欄に打った語で、名前が合う参照だけが候補に出る."""
        ref = LangfusePromptRefFactory(name="companion-skill-good-morning")
        LangfusePromptRefFactory(name="companion-skill-good-night")

        response = admin_site_client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": "companion",
                "model_name": model_name,
                "field_name": field_name,
                "term": "good-morning",
            },
        )

        assert response.status_code == 200
        assert [result["id"] for result in response.json()["results"]] == [str(ref.pk)]


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionConfigAdminSave:
    """設定とスキルをまとめて保存する."""

    def test_add_with_skill_inline_creates_config_and_skill(self, admin_site_client):
        """追加画面から設定とスキルを一度に登録できる."""
        persona = LangfusePromptRefFactory(name="companion-system")
        body = LangfusePromptRefFactory(name="companion-skill-good-morning")
        data = _config_form_data(
            persona,
            **{"skills-TOTAL_FORMS": 1},
            **_skill_form_data(0, "good-morning", body),
        )

        response = admin_site_client.post(
            reverse("admin:companion_companionconfig_add"), data
        )

        assert response.status_code == 302
        config = CompanionConfig.objects.get(name="main")
        assert config.persona_prompt_ref == persona
        assert [(s.name, s.prompt_ref, s.is_enabled) for s in config.skills.all()] == [
            ("good-morning", body, True)
        ]

    def test_add_with_duplicate_skill_names_shows_error_and_saves_nothing(
        self, admin_site_client
    ):
        """同じ名前のスキルを 2 行入れると、エラーを表示して何も保存しない."""
        persona = LangfusePromptRefFactory(name="companion-system")
        body = LangfusePromptRefFactory(name="companion-skill-good-morning")
        data = _config_form_data(
            persona,
            **{"skills-TOTAL_FORMS": 2},
            **_skill_form_data(0, "good-morning", body),
            **_skill_form_data(1, "good-morning", body),
        )

        response = admin_site_client.post(
            reverse("admin:companion_companionconfig_add"), data
        )

        assert response.status_code == 200
        formset = response.context["inline_admin_formsets"][0].formset
        assert formset.non_form_errors()
        assert not CompanionConfig.objects.exists()


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
