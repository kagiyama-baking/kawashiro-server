"""LLMServiceConfig.service_name の choices ラベル「Talk（会話生成）」を「Talk」に変更."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("llm_config", "0008_remove_embedding_service_choice"),
    ]

    operations = [
        migrations.AlterField(
            model_name="llmserviceconfig",
            name="service_name",
            field=models.CharField(
                choices=[
                    ("orchestrator", "HN Agent Orchestrator"),
                    ("detective", "HN Agent Detective"),
                    ("talk", "Talk"),
                ],
                help_text="LLMを使用するサービスの識別名",
                max_length=50,
                unique=True,
                verbose_name="サービス名",
            ),
        ),
    ]
