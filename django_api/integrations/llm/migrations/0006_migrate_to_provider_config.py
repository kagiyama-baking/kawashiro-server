"""データ移行: LLMServiceConfigのmodel_alias/proxy_api_keyをLLMProviderConfigに移行."""

from django.db import migrations


def migrate_forward(apps, schema_editor):
    """既存のLLMServiceConfigデータからLLMProviderConfigを作成しFKを設定."""
    LLMProviderConfig = apps.get_model("llm_config", "LLMProviderConfig")
    LLMServiceConfig = apps.get_model("llm_config", "LLMServiceConfig")

    for service in LLMServiceConfig.objects.all():
        # 同じmodel_alias + encrypted_keyの組み合わせがあれば再利用
        provider, _ = LLMProviderConfig.objects.get_or_create(
            model_alias=service.model_alias,
            defaults={
                "name": service.model_alias,
                "_encrypted_proxy_api_key": service._encrypted_proxy_api_key,
            },
        )
        service.provider_config = provider
        service.save(update_fields=["provider_config"])


def migrate_backward(apps, schema_editor):
    """LLMProviderConfigからLLMServiceConfigにデータを戻す."""
    LLMServiceConfig = apps.get_model("llm_config", "LLMServiceConfig")

    for service in LLMServiceConfig.objects.select_related("provider_config").all():
        if service.provider_config:
            service.model_alias = service.provider_config.model_alias
            service._encrypted_proxy_api_key = (
                service.provider_config._encrypted_proxy_api_key
            )
            service.save(update_fields=["model_alias", "_encrypted_proxy_api_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("llm_config", "0005_add_provider_config"),
    ]

    operations = [
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
