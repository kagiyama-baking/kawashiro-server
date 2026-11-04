"""LLMServiceConfig / LLMProviderConfig モデルのテスト."""

import pytest

from integrations.llm.config import get_llm_settings
from integrations.llm.exceptions import LLMConfigurationError
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

    @pytest.mark.integration
    def test_service_name_with_companion_is_valid_choice(self, provider):
        """companion はサービス名の選択肢にあり（表示名 Companion）、検証を通る.

        objects.create は choices を検証しないので、admin の入力チェックと同じ
        full_clean で確かめる。
        """
        config = LLMServiceConfig(service_name="companion", provider_config=provider)

        config.full_clean()

        assert config.get_service_name_display() == "Companion"

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


@pytest.mark.unit
class TestLLMConfigVerboseNames:
    """管理画面に出す名前（グループ「AI設定」の中で、LLM を重ねない）."""

    def test_service_config_verbose_name_is_service_settings(self):
        """サービスごとの割り当ては「サービス設定」."""
        meta = LLMServiceConfig._meta

        assert (meta.verbose_name, meta.verbose_name_plural) == (
            "サービス設定",
            "サービス設定",
        )

    def test_provider_config_verbose_name_stays_llm_settings(self):
        """モデルと鍵の組は「LLM設定」のまま（サービス設定でそれを選ぶ項目の名前も同じ）."""
        meta = LLMProviderConfig._meta

        assert (meta.verbose_name, meta.verbose_name_plural) == ("LLM設定", "LLM設定")
        assert (
            LLMServiceConfig._meta.get_field("provider_config").verbose_name
            == "LLM設定"
        )


@pytest.mark.integration
@pytest.mark.django_db
def test_get_llm_settings_without_config_raises_error_pointing_to_admin_menu():
    """有効なサービス設定がなければ LLMConfigurationError で、作る場所を今の名前で案内する."""
    with pytest.raises(LLMConfigurationError) as exc_info:
        get_llm_settings("talk")

    message = str(exc_info.value)
    assert "サービス 'talk' のLLM設定がありません" in message
    assert "「AI設定 → サービス設定」" in message
