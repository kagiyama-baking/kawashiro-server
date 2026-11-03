"""LLMServiceConfig.service_name に companion を追加.

既存の talk 設定が存在する場合、同じ provider_config を共有する形で
companion 用の LLMServiceConfig レコードを作成する（is_active=False）。
運用者は管理画面から有効化し、必要なら個別のプロバイダーへ切り替えられる。
"""

from django.db import migrations, models

NEW_SERVICE_NAME = "companion"


def clone_from_talk(apps, schema_editor):
    """talk の LLMServiceConfig を複製して companion 用を作成."""
    LLMServiceConfig = apps.get_model("llm_config", "LLMServiceConfig")

    talk = LLMServiceConfig.objects.filter(service_name="talk").first()
    if talk is None:
        # talk 未設定時は何もしない（運用者が後で管理画面から作成する）
        return

    LLMServiceConfig.objects.get_or_create(
        service_name=NEW_SERVICE_NAME,
        defaults={
            "provider_config": talk.provider_config,
            "is_active": False,
            "timeout": talk.timeout,
        },
    )


def remove_companion_config(apps, schema_editor):
    """複製した companion 用レコードを削除."""
    LLMServiceConfig = apps.get_model("llm_config", "LLMServiceConfig")
    LLMServiceConfig.objects.filter(service_name=NEW_SERVICE_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("llm_config", "0012_add_new_agent_service_choices"),
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
                    ("companion", "Companion"),
                ],
                help_text="LLMを使用するサービスの識別名",
                max_length=50,
                unique=True,
                verbose_name="サービス名",
            ),
        ),
        migrations.RunPython(clone_from_talk, remove_companion_config),
    ]
