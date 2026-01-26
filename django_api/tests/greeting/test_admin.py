"""GreetingConfig admin のテスト"""

import pytest
from django.contrib.admin.sites import AdminSite

from greeting.admin import GreetingConfigAdmin
from greeting.models import GreetingConfig


@pytest.mark.django_db
class TestGreetingConfigAdmin:
    """GreetingConfigAdmin のテスト"""

    def test_admin_is_registered(self):
        """GreetingConfig が admin に登録されている"""
        from django.contrib import admin

        assert GreetingConfig in admin.site._registry

    def test_list_display_contains_expected_fields(self):
        """list_display に必要なフィールドが含まれている"""
        admin_instance = GreetingConfigAdmin(GreetingConfig, AdminSite())

        assert "name" in admin_instance.list_display
        assert "display_name" in admin_instance.list_display
        assert "use_weather" in admin_instance.list_display
        assert "use_events" in admin_instance.list_display
        assert "use_datetime" in admin_instance.list_display
        assert "tts_enabled" in admin_instance.list_display

    def test_fieldsets_organized_properly(self):
        """fieldsets が適切にグループ化されている"""
        admin_instance = GreetingConfigAdmin(GreetingConfig, AdminSite())

        fieldset_names = [name for name, _ in admin_instance.fieldsets]

        # 基本設定、プレースホルダー設定、天気設定、TTS設定、プロンプト設定のセクションがあること
        assert None in fieldset_names  # 基本設定（名前なし）
        assert "プレースホルダー設定" in fieldset_names
        assert "天気設定" in fieldset_names
        assert "TTS設定" in fieldset_names
        assert "プロンプト設定" in fieldset_names

    def test_placeholder_fieldset_has_description(self):
        """プレースホルダー設定セクションに説明がある"""
        admin_instance = GreetingConfigAdmin(GreetingConfig, AdminSite())

        for name, options in admin_instance.fieldsets:
            if name == "プレースホルダー設定":
                assert "description" in options
                break
        else:
            pytest.fail("プレースホルダー設定 fieldset が見つかりません")

    def test_tts_fieldset_has_collapse_class(self):
        """TTS設定セクションは collapse クラスを持つ"""
        admin_instance = GreetingConfigAdmin(GreetingConfig, AdminSite())

        for name, options in admin_instance.fieldsets:
            if name == "TTS設定":
                classes = options.get("classes", [])
                assert "collapse" in classes
                break
        else:
            pytest.fail("TTS設定 fieldset が見つかりません")

    def test_weather_fieldset_has_collapse_class(self):
        """天気設定セクションは collapse クラスを持つ"""
        admin_instance = GreetingConfigAdmin(GreetingConfig, AdminSite())

        for name, options in admin_instance.fieldsets:
            if name == "天気設定":
                classes = options.get("classes", [])
                assert "collapse" in classes
                break
        else:
            pytest.fail("天気設定 fieldset が見つかりません")

    def test_list_filter_contains_placeholder_flags(self):
        """list_filter にプレースホルダーフラグが含まれている"""
        admin_instance = GreetingConfigAdmin(GreetingConfig, AdminSite())

        assert "use_weather" in admin_instance.list_filter
        assert "use_events" in admin_instance.list_filter
        assert "use_datetime" in admin_instance.list_filter
        assert "tts_enabled" in admin_instance.list_filter

    def test_search_fields_contains_name_and_display_name(self):
        """search_fields に name と display_name が含まれている"""
        admin_instance = GreetingConfigAdmin(GreetingConfig, AdminSite())

        assert "name" in admin_instance.search_fields
        assert "display_name" in admin_instance.search_fields
