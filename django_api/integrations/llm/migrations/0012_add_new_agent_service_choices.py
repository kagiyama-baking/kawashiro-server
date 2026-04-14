"""LLMServiceConfig.service_name に devils_advocate / security_responder を追加.

既存の detective 設定が存在する場合、同じ provider_config を共有する形で
新エージェント用の LLMServiceConfig レコードを作成する（is_active=False）。
運用者は管理画面から個別のプロバイダーへ切り替えられる。
"""

from django.db import migrations, models

NEW_SERVICE_NAMES = ("devils_advocate", "security_responder")


def clone_from_detective(apps, schema_editor):
    """detective の LLMServiceConfig を複製して新エージェント用を作成."""
    LLMServiceConfig = apps.get_model("llm_config", "LLMServiceConfig")

    detective = LLMServiceConfig.objects.filter(service_name="detective").first()
    if detective is None:
        # detective 未設定時は何もしない（運用者が後で管理画面から作成する）
        return

    for name in NEW_SERVICE_NAMES:
        LLMServiceConfig.objects.get_or_create(
            service_name=name,
            defaults={
                "provider_config": detective.provider_config,
                "is_active": False,
                "timeout": detective.timeout,
            },
        )


def remove_new_agent_configs(apps, schema_editor):
    """複製した新エージェント用レコードを削除."""
    LLMServiceConfig = apps.get_model("llm_config", "LLMServiceConfig")
    LLMServiceConfig.objects.filter(service_name__in=NEW_SERVICE_NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("llm_config", "0011_remove_openai_config"),
    ]

    operations = [
        migrations.AlterField(
            model_name="llmserviceconfig",
            name="service_name",
            field=models.CharField(
                choices=[
                    ("orchestrator", "HN Agent Orchestrator"),
                    ("detective", "HN Agent Detective"),
                    ("devils_advocate", "HN Agent Devil's Advocate"),
                    ("security_responder", "HN Agent Security Responder"),
                    ("talk", "Talk Generator"),
                ],
                help_text="LLMを使用するサービスの識別名",
                max_length=50,
                unique=True,
                verbose_name="サービス名",
            ),
        ),
        migrations.RunPython(clone_from_detective, remove_new_agent_configs),
    ]
