"""LLMServiceConfig モデルのテスト."""

import pytest

from integrations.llm.models import LLMServiceConfig


@pytest.mark.django_db
class TestLLMServiceConfig:
    """LLMServiceConfig の CRUD テスト."""

    def test_create_config(self):
        """設定を作成できる."""
        config = LLMServiceConfig.objects.create(
            service_name="orchestrator",
            model_alias="gpt-4o",
            is_active=True,
            timeout=60,
        )
        assert config.service_name == "orchestrator"
        assert config.model_alias == "gpt-4o"
        assert config.is_active is True
        assert config.timeout == 60

    def test_service_name_unique(self):
        """service_name はユニーク制約."""
        from django.db import IntegrityError

        LLMServiceConfig.objects.create(
            service_name="talk",
            model_alias="gpt-4o-mini",
        )
        with pytest.raises(IntegrityError):
            LLMServiceConfig.objects.create(
                service_name="talk",
                model_alias="gpt-4o",
            )

    def test_default_values(self):
        """デフォルト値が正しく設定される."""
        config = LLMServiceConfig.objects.create(
            service_name="detective",
            model_alias="gpt-4o-mini",
        )
        assert config.is_active is True
        assert config.timeout == 60

    def test_str_representation(self):
        """文字列表現が正しい."""
        config = LLMServiceConfig(
            service_name="orchestrator",
            model_alias="gpt-4o",
        )
        result = str(config)
        assert "Orchestrator" in result
        assert "gpt-4o" in result

    def test_all_service_choices_valid(self):
        """全てのサービス名で作成できる."""
        services = ["orchestrator", "detective", "talk", "embedding"]
        for service in services:
            config = LLMServiceConfig.objects.create(
                service_name=service,
                model_alias="gpt-4o-mini",
            )
            assert config.service_name == service

    def test_get_active_config_for_service(self):
        """サービス名で有効な設定を取得できる."""
        LLMServiceConfig.objects.create(
            service_name="talk",
            model_alias="gpt-4o-mini",
            is_active=True,
        )
        config = LLMServiceConfig.objects.get(service_name="talk", is_active=True)
        assert config.model_alias == "gpt-4o-mini"

    def test_inactive_config_not_returned(self):
        """非アクティブ設定は取得できない."""
        LLMServiceConfig.objects.create(
            service_name="talk",
            model_alias="gpt-4o-mini",
            is_active=False,
        )
        with pytest.raises(LLMServiceConfig.DoesNotExist):
            LLMServiceConfig.objects.get(service_name="talk", is_active=True)
