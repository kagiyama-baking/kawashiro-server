"""MorningGreetingConfig admin のテスト"""

import pytest
from django.contrib.admin.sites import AdminSite

from greeting.admin import MorningGreetingConfigAdmin
from greeting.models import MorningGreetingConfig


@pytest.mark.django_db
class TestMorningGreetingConfigAdmin:
    """MorningGreetingConfigAdmin のテスト"""

    def test_admin_is_registered(self):
        """MorningGreetingConfig が admin に登録されている"""
        from django.contrib import admin

        assert MorningGreetingConfig in admin.site._registry

    def test_list_display_contains_expected_fields(self):
        """list_display に必要なフィールドが含まれている"""
        admin_instance = MorningGreetingConfigAdmin(MorningGreetingConfig, AdminSite())

        assert "area_code" in admin_instance.list_display
        assert "tts_enabled" in admin_instance.list_display

    def test_fieldsets_organized_properly(self):
        """fieldsets が適切にグループ化されている"""
        admin_instance = MorningGreetingConfigAdmin(MorningGreetingConfig, AdminSite())

        fieldset_names = [name for name, _ in admin_instance.fieldsets]

        # 基本設定、TTS設定、プロンプト設定のセクションがあること
        assert None in fieldset_names  # 基本設定（名前なし）
        assert "TTS設定" in fieldset_names
        assert "プロンプト設定" in fieldset_names

    def test_tts_fieldset_has_collapse_class(self):
        """TTS設定セクションは collapse クラスを持つ"""
        admin_instance = MorningGreetingConfigAdmin(MorningGreetingConfig, AdminSite())

        for name, options in admin_instance.fieldsets:
            if name == "TTS設定":
                classes = options.get("classes", [])
                assert "collapse" in classes
                break
        else:
            pytest.fail("TTS設定 fieldset が見つかりません")

    def test_has_add_permission_false_when_config_exists(self):
        """設定が既に存在する場合は追加不可"""
        MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="テスト",
            user_prompt="テスト",
        )

        admin_instance = MorningGreetingConfigAdmin(MorningGreetingConfig, AdminSite())

        class MockRequest:
            pass

        assert admin_instance.has_add_permission(MockRequest()) is False

    def test_has_add_permission_true_when_no_config(self):
        """設定が存在しない場合は追加可能"""
        admin_instance = MorningGreetingConfigAdmin(MorningGreetingConfig, AdminSite())

        class MockUser:
            def has_perm(self, perm):
                return True

        class MockRequest:
            user = MockUser()

        assert admin_instance.has_add_permission(MockRequest()) is True

    def test_has_delete_permission_always_false(self):
        """削除は常に不可"""
        admin_instance = MorningGreetingConfigAdmin(MorningGreetingConfig, AdminSite())

        class MockRequest:
            pass

        assert admin_instance.has_delete_permission(MockRequest()) is False
