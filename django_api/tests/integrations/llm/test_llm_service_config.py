"""LLMServiceConfig / LLMProviderConfig モデルのテスト."""

import pytest

from integrations.llm.models import LLMProviderConfig, LLMServiceConfig


@pytest.fixture
def provider():
    """テスト用のLLMProviderConfig."""
    return LLMProviderConfig.objects.create(
        name="テスト用GPT-4o",
        model_alias="gpt-4o",
    )


@pytest.fixture
def provider_embedding():
    """テスト用のEmbeddingプロバイダー."""
    return LLMProviderConfig.objects.create(
        name="テスト用Embedding",
        model_alias="text-embedding-3-small",
    )


@pytest.mark.django_db
class TestLLMProviderConfig:
    """LLMProviderConfig の CRUD テスト."""

    def test_create_provider(self):
        """プロバイダー設定を作成できる."""
        provider = LLMProviderConfig.objects.create(
            name="Kimi K2.5 本番",
            model_alias="bedrock/moonshotai.kimi-k2.5",
        )
        assert provider.name == "Kimi K2.5 本番"
        assert provider.model_alias == "bedrock/moonshotai.kimi-k2.5"

    def test_str_representation(self):
        """文字列表現にname+model_aliasが含まれる."""
        provider = LLMProviderConfig(
            name="Kimi K2.5",
            model_alias="bedrock/moonshotai.kimi-k2.5",
        )
        result = str(provider)
        assert "Kimi K2.5" in result
        assert "bedrock/moonshotai.kimi-k2.5" in result

    def test_name_unique(self):
        """nameはユニーク制約."""
        from django.db import IntegrityError

        LLMProviderConfig.objects.create(name="GPT-4o", model_alias="gpt-4o")
        with pytest.raises(IntegrityError):
            LLMProviderConfig.objects.create(name="GPT-4o", model_alias="gpt-4o-mini")


@pytest.mark.django_db
class TestLLMServiceConfig:
    """LLMServiceConfig の CRUD テスト."""

    def test_create_config(self, provider):
        """設定を作成できる."""
        config = LLMServiceConfig.objects.create(
            service_name="orchestrator",
            provider_config=provider,
            is_active=True,
            timeout=60,
        )
        assert config.service_name == "orchestrator"
        assert config.provider_config == provider
        assert config.is_active is True
        assert config.timeout == 60

    def test_service_name_unique(self, provider):
        """service_name はユニーク制約."""
        from django.db import IntegrityError

        LLMServiceConfig.objects.create(
            service_name="talk",
            provider_config=provider,
        )
        with pytest.raises(IntegrityError):
            LLMServiceConfig.objects.create(
                service_name="talk",
                provider_config=provider,
            )

    def test_default_values(self, provider):
        """デフォルト値が正しく設定される."""
        config = LLMServiceConfig.objects.create(
            service_name="detective",
            provider_config=provider,
        )
        assert config.is_active is True
        assert config.timeout == 60

    def test_str_representation(self, provider):
        """文字列表現が正しい."""
        config = LLMServiceConfig(
            service_name="orchestrator",
            provider_config=provider,
        )
        result = str(config)
        assert "Orchestrator" in result
        assert provider.name in result

    def test_all_service_choices_valid(self, provider):
        """全てのサービス名で作成できる."""
        services = ["orchestrator", "detective", "talk", "embedding"]
        for service in services:
            config = LLMServiceConfig.objects.create(
                service_name=service,
                provider_config=provider,
            )
            assert config.service_name == service

    def test_shared_provider(self, provider):
        """複数サービスが同じプロバイダー設定を共有できる."""
        talk = LLMServiceConfig.objects.create(
            service_name="talk", provider_config=provider
        )
        detective = LLMServiceConfig.objects.create(
            service_name="detective", provider_config=provider
        )
        assert talk.provider_config_id == detective.provider_config_id

    def test_get_active_config_for_service(self, provider):
        """サービス名で有効な設定を取得できる."""
        LLMServiceConfig.objects.create(
            service_name="talk",
            provider_config=provider,
            is_active=True,
        )
        config = LLMServiceConfig.objects.select_related("provider_config").get(
            service_name="talk", is_active=True
        )
        assert config.provider_config.model_alias == "gpt-4o"

    def test_inactive_config_not_returned(self, provider):
        """非アクティブ設定は取得できない."""
        LLMServiceConfig.objects.create(
            service_name="talk",
            provider_config=provider,
            is_active=False,
        )
        with pytest.raises(LLMServiceConfig.DoesNotExist):
            LLMServiceConfig.objects.get(service_name="talk", is_active=True)

    def test_protect_on_delete(self, provider):
        """使用中のプロバイダー設定は削除できない."""
        from django.db.models import ProtectedError

        LLMServiceConfig.objects.create(service_name="talk", provider_config=provider)
        with pytest.raises(ProtectedError):
            provider.delete()
