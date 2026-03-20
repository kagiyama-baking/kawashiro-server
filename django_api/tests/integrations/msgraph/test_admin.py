"""Microsoft Graph API設定管理画面のテスト"""

import pytest
from django import forms
from django.test import override_settings

from integrations.msgraph.admin import MSGraphConfigForm
from integrations.msgraph.models import MSGraphConfig


@pytest.mark.django_db
class TestMSGraphConfigForm:
    """MSGraphConfigFormのテスト"""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-admin-tests")
    def test_form_save_with_private_key(self):
        """秘密鍵を含むフォームが正常に保存されること"""
        form_data = {
            "name": "テスト設定",
            "is_active": False,
            "tenant_id": "test-tenant-id",
            "client_id": "test-client-id",
            "cert_thumbprint": "test-thumbprint",
            "target_user": "test@example.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        }

        form = MSGraphConfigForm(data=form_data)
        assert form.is_valid(), form.errors

        instance = form.save()

        assert instance.pk is not None
        assert (
            instance.private_key
            == "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
        )
        assert instance._encrypted_private_key != ""
        assert instance._encrypted_private_key != form_data["private_key"]

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-admin-tests")
    def test_form_save_without_private_key(self):
        """秘密鍵なしでフォームが正常に保存されること"""
        form_data = {
            "name": "テスト設定",
            "is_active": False,
            "tenant_id": "test-tenant-id",
            "client_id": "test-client-id",
            "cert_thumbprint": "test-thumbprint",
            "target_user": "test@example.com",
            "private_key": "",
        }

        form = MSGraphConfigForm(data=form_data)
        assert form.is_valid(), form.errors

        instance = form.save()

        assert instance.pk is not None
        assert instance.private_key == ""
        assert instance._encrypted_private_key == ""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-admin-tests")
    def test_form_update_preserves_existing_private_key(self):
        """秘密鍵フィールドが空の場合、既存の秘密鍵が保持されること"""
        # 既存の設定を作成
        config = MSGraphConfig.objects.create(
            name="既存設定",
            tenant_id="existing-tenant",
            client_id="existing-client",
            cert_thumbprint="existing-thumb",
            target_user="existing@example.com",
        )
        config.private_key = (
            "-----BEGIN PRIVATE KEY-----\nexisting\n-----END PRIVATE KEY-----"
        )
        config.save()

        original_encrypted = config._encrypted_private_key

        # 秘密鍵なしで更新
        form_data = {
            "name": "既存設定",
            "is_active": False,
            "tenant_id": "updated-tenant",
            "client_id": "updated-client",
            "cert_thumbprint": "updated-thumb",
            "target_user": "updated@example.com",
            "private_key": "",  # 空のまま
        }

        form = MSGraphConfigForm(data=form_data, instance=config)
        assert form.is_valid(), form.errors

        instance = form.save()

        # 秘密鍵は変更されていないこと
        assert instance._encrypted_private_key == original_encrypted
        assert (
            instance.private_key
            == "-----BEGIN PRIVATE KEY-----\nexisting\n-----END PRIVATE KEY-----"
        )

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-admin-tests")
    def test_form_help_text_for_new_config(self):
        """新規設定の場合のヘルプテキスト"""
        form = MSGraphConfigForm()

        assert (
            form.fields["private_key"].help_text
            == "PEM形式の秘密鍵を入力してください。空のままにすると既存の値を保持します。"
        )

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-admin-tests")
    def test_form_help_text_for_existing_config_with_key(self):
        """秘密鍵が設定済みの既存設定の場合のヘルプテキスト"""
        config = MSGraphConfig.objects.create(
            name="既存設定",
            tenant_id="existing-tenant",
            client_id="existing-client",
            cert_thumbprint="existing-thumb",
            target_user="existing@example.com",
        )
        config.private_key = (
            "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
        )
        config.save()

        form = MSGraphConfigForm(instance=config)

        assert (
            form.fields["private_key"].help_text
            == "秘密鍵は既に設定されています。変更する場合のみ入力してください。"
        )

    @override_settings(ENCRYPTION_KEY="short")  # 32文字未満
    def test_form_save_raises_validation_error_on_encryption_failure(self):
        """暗号化失敗時にValidationErrorが発生すること"""
        form_data = {
            "name": "テスト設定",
            "is_active": False,
            "tenant_id": "test-tenant-id",
            "client_id": "test-client-id",
            "cert_thumbprint": "test-thumbprint",
            "target_user": "test@example.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        }

        form = MSGraphConfigForm(data=form_data)
        assert form.is_valid(), form.errors

        with pytest.raises(forms.ValidationError) as exc_info:
            form.save()

        assert "秘密鍵の暗号化に失敗しました" in str(exc_info.value)


@pytest.mark.django_db
class TestMSGraphConfigAdmin:
    """MSGraphConfigAdminのテスト"""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-admin-tests")
    def test_activate_config_action_single_selection(self):
        """activate_configアクションが1つの設定を有効にすること"""
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        from integrations.msgraph.admin import MSGraphConfigAdmin

        config1 = MSGraphConfig.objects.create(
            name="設定1",
            tenant_id="tenant-1",
            client_id="client-1",
            cert_thumbprint="thumb-1",
            target_user="user1@example.com",
            is_active=True,
        )
        config2 = MSGraphConfig.objects.create(
            name="設定2",
            tenant_id="tenant-2",
            client_id="client-2",
            cert_thumbprint="thumb-2",
            target_user="user2@example.com",
            is_active=False,
        )

        admin_site = AdminSite()
        model_admin = MSGraphConfigAdmin(MSGraphConfig, admin_site)
        request = RequestFactory().post("/admin/")
        request.session = "session"
        request._messages = FallbackStorage(request)

        # config2を選択してアクション実行
        queryset = MSGraphConfig.objects.filter(pk=config2.pk)
        model_admin.activate_config(request, queryset)

        config1.refresh_from_db()
        config2.refresh_from_db()

        assert config1.is_active is False
        assert config2.is_active is True

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-admin-tests")
    def test_activate_config_action_multiple_selection_fails(self):
        """activate_configアクションが複数選択時にエラーとなること"""
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        from integrations.msgraph.admin import MSGraphConfigAdmin

        MSGraphConfig.objects.create(
            name="設定1",
            tenant_id="tenant-1",
            client_id="client-1",
            cert_thumbprint="thumb-1",
            target_user="user1@example.com",
        )
        MSGraphConfig.objects.create(
            name="設定2",
            tenant_id="tenant-2",
            client_id="client-2",
            cert_thumbprint="thumb-2",
            target_user="user2@example.com",
        )

        admin_site = AdminSite()
        model_admin = MSGraphConfigAdmin(MSGraphConfig, admin_site)
        request = RequestFactory().post("/admin/")
        request.session = "session"
        request._messages = FallbackStorage(request)

        # 両方を選択してアクション実行
        queryset = MSGraphConfig.objects.all()
        model_admin.activate_config(request, queryset)

        # どちらも有効化されていないこと
        assert MSGraphConfig.objects.filter(is_active=True).count() == 0
