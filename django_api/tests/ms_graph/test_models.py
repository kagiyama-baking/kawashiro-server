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
        from ms_graph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant-id",
            client_id="test-client-id",
            cert_thumbprint="test-thumbprint",
            target_user="test@example.com",
        )

        assert config.pk is not None
        assert config.name == "テスト設定"
        assert config.tenant_id == "test-tenant-id"
        assert config.client_id == "test-client-id"
        assert config.cert_thumbprint == "test-thumbprint"
        assert config.target_user == "test@example.com"
        assert config.is_active is False  # デフォルトは無効

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_create_multiple_configs(self):
        """複数の設定を作成できること"""
        from ms_graph.models import MSGraphConfig

        config1 = MSGraphConfig.objects.create(
            name="設定1",
            tenant_id="tenant-1",
            client_id="client-1",
            cert_thumbprint="thumb-1",
            target_user="user1@example.com",
        )
        config2 = MSGraphConfig.objects.create(
            name="設定2",
            tenant_id="tenant-2",
            client_id="client-2",
            cert_thumbprint="thumb-2",
            target_user="user2@example.com",
        )

        assert MSGraphConfig.objects.count() == 2
        assert config1.pk != config2.pk

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_unique_name_constraint(self):
        """設定名が一意であること"""
        from ms_graph.models import MSGraphConfig

        MSGraphConfig.objects.create(
            name="同じ名前",
            tenant_id="tenant-1",
            client_id="client-1",
            cert_thumbprint="thumb-1",
            target_user="user1@example.com",
        )

        with pytest.raises(IntegrityError):
            MSGraphConfig.objects.create(
                name="同じ名前",
                tenant_id="tenant-2",
                client_id="client-2",
                cert_thumbprint="thumb-2",
                target_user="user2@example.com",
            )

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_only_one_active_config(self):
        """有効な設定は1つだけであること"""
        from ms_graph.models import MSGraphConfig

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
            is_active=True,
        )

        # config2を有効にすると、config1は自動的に無効になる
        config1.refresh_from_db()
        assert config1.is_active is False
        assert config2.is_active is True

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_activate_config(self):
        """設定を有効化できること"""
        from ms_graph.models import MSGraphConfig

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
        )

        # config2を有効化
        config2.is_active = True
        config2.save()

        config1.refresh_from_db()
        config2.refresh_from_db()

        assert config1.is_active is False
        assert config2.is_active is True

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_get_active_config(self):
        """有効な設定を取得できること"""
        from ms_graph.models import MSGraphConfig

        MSGraphConfig.objects.create(
            name="無効な設定",
            tenant_id="tenant-1",
            client_id="client-1",
            cert_thumbprint="thumb-1",
            target_user="user1@example.com",
            is_active=False,
        )
        active_config = MSGraphConfig.objects.create(
            name="有効な設定",
            tenant_id="tenant-2",
            client_id="client-2",
            cert_thumbprint="thumb-2",
            target_user="user2@example.com",
            is_active=True,
        )

        result = MSGraphConfig.objects.get_active_config()
        assert result.pk == active_config.pk
        assert result.name == "有効な設定"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_get_active_config_raises_when_none_active(self):
        """有効な設定がない場合にDoesNotExistが発生すること"""
        from ms_graph.models import MSGraphConfig

        MSGraphConfig.objects.create(
            name="無効な設定",
            tenant_id="tenant-1",
            client_id="client-1",
            cert_thumbprint="thumb-1",
            target_user="user1@example.com",
            is_active=False,
        )

        with pytest.raises(MSGraphConfig.DoesNotExist):
            MSGraphConfig.objects.get_active_config()

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_private_key_encryption(self):
        """秘密鍵が暗号化されて保存されること"""
        from ms_graph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        original_key = (
            "-----BEGIN PRIVATE KEY-----\ntest-key-content\n-----END PRIVATE KEY-----"
        )
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
        from ms_graph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        assert config.private_key == ""
        assert config._encrypted_private_key == ""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_str_representation(self):
        """__str__が設定名を返すこと"""
        from ms_graph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="本番環境設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        assert str(config) == "本番環境設定"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_str_representation_with_active_status(self):
        """__str__が有効状態を含むこと"""
        from ms_graph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="本番環境設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
            is_active=True,
        )

        assert "本番環境設定" in str(config)
        assert "有効" in str(config)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_verbose_name(self):
        """verbose_nameが正しいこと"""
        from ms_graph.models import MSGraphConfig

        assert MSGraphConfig._meta.verbose_name == "Microsoft Graph API設定"
        assert MSGraphConfig._meta.verbose_name_plural == "Microsoft Graph API設定"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-model-tests")
    def test_timestamps_auto_set(self):
        """タイムスタンプが自動設定されること"""
        from ms_graph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
        )

        assert config.created_at is not None
        assert config.updated_at is not None
