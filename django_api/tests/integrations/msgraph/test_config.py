"""設定取得ヘルパーのテスト"""

import pytest
from django.test import override_settings

from integrations.msgraph.exceptions import ConfigurationError


@pytest.mark.django_db
class TestGetMSGraphSettings:
    """get_ms_graph_settings関数のテスト"""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_success(self):
        """有効な設定を正常に取得できること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
            is_active=True,
        )
        config.private_key = "test-private-key"
        config.save()

        settings = get_ms_graph_settings()

        assert settings.tenant_id == "test-tenant"
        assert settings.client_id == "test-client"
        assert settings.cert_thumbprint == "test-thumb"
        assert settings.private_key == "test-private-key"
        assert settings.target_user == "test@example.com"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_returns_active_config(self):
        """複数設定がある場合に有効な設定が返されること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        # 無効な設定
        inactive = MSGraphConfig.objects.create(
            name="無効な設定",
            tenant_id="inactive-tenant",
            client_id="inactive-client",
            cert_thumbprint="inactive-thumb",
            target_user="inactive@example.com",
            is_active=False,
        )
        inactive.private_key = "inactive-key"
        inactive.save()

        # 有効な設定
        active = MSGraphConfig.objects.create(
            name="有効な設定",
            tenant_id="active-tenant",
            client_id="active-client",
            cert_thumbprint="active-thumb",
            target_user="active@example.com",
            is_active=True,
        )
        active.private_key = "active-key"
        active.save()

        settings = get_ms_graph_settings()

        assert settings.tenant_id == "active-tenant"
        assert settings.client_id == "active-client"

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_no_active_config(self):
        """有効な設定がない場合にConfigurationErrorが発生すること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        MSGraphConfig.objects.create(
            name="無効な設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
            is_active=False,
        )

        with pytest.raises(ConfigurationError) as excinfo:
            get_ms_graph_settings()
        assert "有効なMicrosoft Graph API設定がありません" in str(excinfo.value)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_not_exists(self):
        """設定が存在しない場合にConfigurationErrorが発生すること"""
        from integrations.msgraph.config import get_ms_graph_settings

        with pytest.raises(ConfigurationError) as excinfo:
            get_ms_graph_settings()
        assert "有効なMicrosoft Graph API設定がありません" in str(excinfo.value)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_missing_tenant_id(self):
        """テナントIDが空の場合にConfigurationErrorが発生すること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="",  # 空
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
            is_active=True,
        )
        config.private_key = "test-key"
        config.save()

        with pytest.raises(ConfigurationError) as excinfo:
            get_ms_graph_settings()
        assert "テナントID" in str(excinfo.value)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_missing_client_id(self):
        """クライアントIDが空の場合にConfigurationErrorが発生すること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant",
            client_id="",  # 空
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
            is_active=True,
        )
        config.private_key = "test-key"
        config.save()

        with pytest.raises(ConfigurationError) as excinfo:
            get_ms_graph_settings()
        assert "クライアントID" in str(excinfo.value)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_missing_cert_thumbprint(self):
        """証明書サムプリントが空の場合にConfigurationErrorが発生すること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="",  # 空
            target_user="test@example.com",
            is_active=True,
        )
        config.private_key = "test-key"
        config.save()

        with pytest.raises(ConfigurationError) as excinfo:
            get_ms_graph_settings()
        assert "証明書サムプリント" in str(excinfo.value)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_missing_private_key(self):
        """秘密鍵が空の場合にConfigurationErrorが発生すること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
            is_active=True,
            # private_key は設定しない
        )

        with pytest.raises(ConfigurationError) as excinfo:
            get_ms_graph_settings()
        assert "秘密鍵" in str(excinfo.value)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_missing_target_user(self):
        """対象ユーザーが空の場合にConfigurationErrorが発生すること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="test-tenant",
            client_id="test-client",
            cert_thumbprint="test-thumb",
            target_user="",  # 空
            is_active=True,
        )
        config.private_key = "test-key"
        config.save()

        with pytest.raises(ConfigurationError) as excinfo:
            get_ms_graph_settings()
        assert "対象ユーザー" in str(excinfo.value)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_get_settings_multiple_missing_fields(self):
        """複数のフィールドが空の場合にすべてがエラーメッセージに含まれること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="",  # 空
            client_id="",  # 空
            cert_thumbprint="test-thumb",
            target_user="test@example.com",
            is_active=True,
            # private_key は設定しない
        )

        with pytest.raises(ConfigurationError) as excinfo:
            get_ms_graph_settings()
        error_message = str(excinfo.value)
        assert "テナントID" in error_message
        assert "クライアントID" in error_message
        assert "秘密鍵" in error_message


@pytest.mark.django_db
class TestMSGraphSettingsDataclass:
    """MSGraphSettingsデータクラスのテスト"""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-config-tests")
    def test_dataclass_attributes(self):
        """データクラスの属性が正しく設定されること"""
        from integrations.msgraph.config import get_ms_graph_settings
        from integrations.msgraph.models import MSGraphConfig

        config = MSGraphConfig.objects.create(
            name="テスト設定",
            tenant_id="tenant-123",
            client_id="client-456",
            cert_thumbprint="thumb-789",
            target_user="user@example.com",
            is_active=True,
        )
        config.private_key = (
            "-----BEGIN PRIVATE KEY-----\nkey-content\n-----END PRIVATE KEY-----"
        )
        config.save()

        settings = get_ms_graph_settings()

        # データクラスの属性が正しいか確認
        assert hasattr(settings, "tenant_id")
        assert hasattr(settings, "client_id")
        assert hasattr(settings, "cert_thumbprint")
        assert hasattr(settings, "private_key")
        assert hasattr(settings, "target_user")
