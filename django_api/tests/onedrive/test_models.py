"""MSGraphConfigモデルのテスト"""

import pytest
from django.db import IntegrityError
from django.test import override_settings


@pytest.mark.django_db
class TestMSGraphConfigModel:
    """MSGraphConfigモデルのテスト"""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_create_config(self):
        """設定を作成できること"""
        from onedrive.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            tenant_id="test-tenant-id",
            client_id="test-client-id",
            cert_thumbprint="test-thumbprint",
            target_user="test@example.com",
        )

        assert config.pk == 1
        assert config.tenant_id == "test-tenant-id"
        assert config.client_id == "test-client-id"
        assert config.cert_thumbprint == "test-thumbprint"
        assert config.target_user == "test@example.com"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_singleton_pk_is_always_one(self):
        """pkが常に1になること（シングルトン）"""
        from onedrive.models import MSGraphConfig

        config = MSGraphConfig(
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )
        config.save()

        assert config.pk == 1

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_singleton_constraint_on_create(self):
        """2つ目の設定を作成しようとするとIntegrityErrorになること"""
        from onedrive.models import MSGraphConfig

        MSGraphConfig.objects.create(
            tenant_id="first-tenant",
            client_id="first-client",
            cert_thumbprint="first-thumb",
            target_user="first@example.com",
        )

        with pytest.raises(IntegrityError):
            MSGraphConfig.objects.create(
                tenant_id="second-tenant",
                client_id="second-client",
                cert_thumbprint="second-thumb",
                target_user="second@example.com",
            )

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_update_existing_config(self):
        """既存の設定を更新できること"""
        from onedrive.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            tenant_id="original-tenant",
            client_id="original-client",
            cert_thumbprint="original-thumb",
            target_user="original@example.com",
        )

        config.tenant_id = "updated-tenant"
        config.save()

        config.refresh_from_db()
        assert config.tenant_id == "updated-tenant"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_private_key_encryption(self):
        """秘密鍵が暗号化されて保存されること"""
        from onedrive.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        original_key = "-----BEGIN PRIVATE KEY-----\ntest-key-content\n-----END PRIVATE KEY-----"
        config.private_key = original_key
        config.save()

        # DBから再取得
        config.refresh_from_db()

        # 暗号化されていることを確認（内部フィールドが元の値と異なる）
        assert config._encrypted_private_key != original_key
        assert config._encrypted_private_key != ""

        # 復号化できることを確認
        assert config.private_key == original_key

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_private_key_empty_by_default(self):
        """秘密鍵がデフォルトで空であること"""
        from onedrive.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        assert config.private_key == ""
        assert config._encrypted_private_key == ""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_str_representation(self):
        """__str__が正しい文字列を返すこと"""
        from onedrive.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        assert str(config) == "Microsoft Graph API設定"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_verbose_name(self):
        """verbose_nameが正しいこと"""
        from onedrive.models import MSGraphConfig

        assert MSGraphConfig._meta.verbose_name == "Microsoft Graph API設定"
        assert MSGraphConfig._meta.verbose_name_plural == "Microsoft Graph API設定"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_timestamps_auto_set(self):
        """タイムスタンプが自動設定されること"""
        from onedrive.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        assert config.created_at is not None
        assert config.updated_at is not None

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_get_config_method(self):
        """objects.get_config()で設定を取得できること"""
        from onedrive.models import MSGraphConfig

        MSGraphConfig.objects.create(
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        config = MSGraphConfig.objects.get_config()
        assert config.tenant_id == "test-tenant"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_get_config_raises_when_not_exists(self):
        """設定が存在しない場合にDoesNotExistが発生すること"""
        from onedrive.models import MSGraphConfig

        with pytest.raises(MSGraphConfig.DoesNotExist):
            MSGraphConfig.objects.get_config()
