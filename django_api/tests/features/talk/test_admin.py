"""Talk の admin のテスト（Talk 設定・チャットセッション）."""

import pytest
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.urls import NoReverseMatch, reverse

from features.talk.models import ChatSession
from tests.fixtures.factories import AgentSkillFactory, TalkSettingFactory


def _content(response) -> str:
    return response.content.decode()


@pytest.mark.integration
@pytest.mark.django_db
class TestTalkAdminRegistry:
    """Talk の admin に出るモデル（旧会話生成設定はない）."""

    def test_admin_registers_talk_setting_and_chat_history_only(self):
        """Talk のグループは Talk 設定とチャット履歴だけ."""
        registered = {
            model._meta.object_name
            for model in admin.site._registry
            if model._meta.app_label == "talk"
        }

        assert registered == {"TalkSetting", "ChatSession", "ChatMessage"}

    def test_talk_config_changelist_url_cannot_be_reversed(self):
        """旧会話生成設定の一覧の URL 名は引けない."""
        with pytest.raises(NoReverseMatch):
            reverse("admin:talk_talkconfig_changelist")

    def test_talk_config_changelist_path_returns_404(self, admin_site_client):
        """旧会話生成設定の一覧のパスは 404."""
        response = admin_site_client.get("/admin/talk/talkconfig/")

        assert response.status_code == 404


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

    def test_change_page_shows_setting_and_scene_read_only(
        self, admin_site_client, superuser
    ):
        """Talk 設定とシーンは読み取り専用（作成時に固定）."""
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
        assert {"setting", "skill"}.isdisjoint(form_fields)
        content = _content(response)
        assert "ひな" in content
        assert "talk-scene-cafe" in content

    def test_add_page_lets_setting_and_scene_be_chosen(self, admin_site_client):
        """admin で作るチャットは、Talk 設定とシーンをここで選ぶ（作った後は読み取り専用）."""
        response = admin_site_client.get(reverse("admin:talk_chatsession_add"))

        assert response.status_code == 200
        form_fields = response.context["adminform"].form.fields
        assert {"setting", "skill"} <= set(form_fields)

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
