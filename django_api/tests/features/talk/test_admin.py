"""Talk の admin のテスト（会話生成設定・Talk 設定・チャットセッション）"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.urls import reverse

from features.talk.admin import TalkConfigAdmin
from features.talk.models import ChatSession, TalkConfig
from tests.fixtures.factories import AgentSkillFactory, TalkSettingFactory


@pytest.mark.django_db
class TestTalkConfigAdmin:
    """TalkConfigAdmin のテスト"""

    def test_admin_is_registered(self):
        """TalkConfig が admin に登録されている"""
        from django.contrib import admin

        assert TalkConfig in admin.site._registry

    def test_list_display_contains_expected_fields(self):
        """list_display に必要なフィールドが含まれている"""
        admin_instance = TalkConfigAdmin(TalkConfig, AdminSite())

        assert "name" in admin_instance.list_display
        assert "display_name" in admin_instance.list_display
        assert "tts_enabled" in admin_instance.list_display

    def test_fieldsets_organized_properly(self):
        """fieldsets が適切にグループ化されている."""
        admin_instance = TalkConfigAdmin(TalkConfig, AdminSite())

        fieldset_names = [name for name, _ in admin_instance.fieldsets]

        assert None in fieldset_names  # 基本設定（名前なし）
        assert "天気設定" in fieldset_names
        assert "TTS設定" in fieldset_names
        assert "プロンプト参照（Langfuse）" in fieldset_names
        assert "回数制限" in fieldset_names

    def test_rate_limit_fieldset_shows_synthesize_rate_limit(self):
        """回数制限の節に生成回数の上限があり、畳まずに見せる."""
        admin_instance = TalkConfigAdmin(TalkConfig, AdminSite())

        options = dict(admin_instance.fieldsets)["回数制限"]

        assert options["fields"] == ("synthesize_rate_limit",)
        assert "collapse" not in options.get("classes", ())

    def test_tts_fieldset_has_collapse_class(self):
        """TTS設定セクションは collapse クラスを持つ"""
        admin_instance = TalkConfigAdmin(TalkConfig, AdminSite())

        for name, options in admin_instance.fieldsets:
            if name == "TTS設定":
                classes = options.get("classes", [])
                assert "collapse" in classes
                break
        else:
            pytest.fail("TTS設定 fieldset が見つかりません")

    def test_weather_fieldset_has_collapse_class(self):
        """天気設定セクションは collapse クラスを持つ"""
        admin_instance = TalkConfigAdmin(TalkConfig, AdminSite())

        for name, options in admin_instance.fieldsets:
            if name == "天気設定":
                classes = options.get("classes", [])
                assert "collapse" in classes
                break
        else:
            pytest.fail("天気設定 fieldset が見つかりません")

    def test_list_filter_contains_tts_enabled(self):
        """list_filter に tts_enabled が含まれている"""
        admin_instance = TalkConfigAdmin(TalkConfig, AdminSite())

        assert "tts_enabled" in admin_instance.list_filter

    def test_search_fields_contains_name_and_display_name(self):
        """search_fields に name と display_name が含まれている"""
        admin_instance = TalkConfigAdmin(TalkConfig, AdminSite())

        assert "name" in admin_instance.search_fields
        assert "display_name" in admin_instance.search_fields


def _content(response) -> str:
    return response.content.decode()


@pytest.mark.integration
@pytest.mark.django_db
class TestTalkSettingAdminPages:
    """Talk 設定の一覧・追加・変更の画面."""

    def test_changelist_for_superuser_lists_settings(self, admin_site_client):
        """一覧に設定が並ぶ."""
        TalkSettingFactory(name="ひな")

        response = admin_site_client.get(reverse("admin:talk_talksetting_changelist"))

        assert response.status_code == 200
        assert "ひな" in _content(response)

    def test_add_page_explains_multiple_enabled_settings_and_llm_connection(
        self, admin_site_client
    ):
        """基本設定の説明で、複数を有効にできることと LLM の接続先を案内する."""
        response = admin_site_client.get(reverse("admin:talk_talksetting_add"))

        content = _content(response)
        assert response.status_code == 200
        assert "複数の設定を有効にできます" in content
        assert "「AI設定 → サービス設定」の Talk で管理します" in content

    def test_change_page_scenes_use_filtered_select_multiple_with_name_and_label(
        self, admin_site_client
    ):
        """シーンは、登録済みのスキルから左右の一覧で選ぶ（スキル名@ラベルで出る）."""
        AgentSkillFactory(name="talk-scene-cafe", label="staging")
        setting = TalkSettingFactory()

        response = admin_site_client.get(
            reverse("admin:talk_talksetting_change", args=[setting.pk])
        )

        field = response.context["adminform"].form.fields["skills"]
        assert isinstance(field.widget.widget, FilteredSelectMultiple)
        assert "talk-scene-cafe@staging" in _content(response)


@pytest.mark.integration
@pytest.mark.django_db
class TestChatSessionAdminTalkSetting:
    """チャットセッションの画面の Talk 設定とシーン."""

    def test_change_page_shows_setting_scene_and_preset_name_read_only(
        self, admin_site_client, superuser
    ):
        """Talk 設定・シーン・旧プリセット名は読み取り専用（作成時に固定）."""
        scene = AgentSkillFactory(name="talk-scene-cafe")
        setting = TalkSettingFactory(name="ひな", skills=[scene])
        session = ChatSession.objects.create(
            user=superuser, setting=setting, skill=scene, title="カフェで"
        )

        response = admin_site_client.get(
            reverse("admin:talk_chatsession_change", args=[session.pk])
        )

        assert response.status_code == 200
        form_fields = response.context["adminform"].form.fields
        assert {"setting", "skill", "config_name"}.isdisjoint(form_fields)
        content = _content(response)
        assert "ひな" in content
        assert "talk-scene-cafe" in content

    def test_add_page_lets_setting_and_scene_be_chosen(self, admin_site_client):
        """admin で作るチャットは、Talk 設定とシーンをここで選ぶ（作った後は読み取り専用）."""
        response = admin_site_client.get(reverse("admin:talk_chatsession_add"))

        assert response.status_code == 200
        form_fields = response.context["adminform"].form.fields
        assert {"setting", "skill"} <= set(form_fields)
        assert "config_name" not in form_fields

    def test_changelist_shows_setting_and_scene_columns(
        self, admin_site_client, superuser
    ):
        """一覧に Talk 設定とシーンの列がある."""
        setting = TalkSettingFactory(name="ひな")
        ChatSession.objects.create(user=superuser, setting=setting, title="一覧の確認")

        response = admin_site_client.get(reverse("admin:talk_chatsession_changelist"))

        assert response.status_code == 200
        assert "column-setting" in _content(response)
        assert "column-skill" in _content(response)
