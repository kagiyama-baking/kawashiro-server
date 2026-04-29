"""TalkConfig admin のテスト"""

import pytest
from django.contrib.admin.sites import AdminSite

from features.talk.admin import TalkConfigAdmin
from features.talk.models import TalkConfig


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
