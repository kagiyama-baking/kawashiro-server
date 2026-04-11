"""旧フィールド削除 + provider_config FKをnot null化."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("llm_config", "0006_migrate_to_provider_config"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="llmserviceconfig",
            name="_encrypted_proxy_api_key",
        ),
        migrations.RemoveField(
            model_name="llmserviceconfig",
            name="model_alias",
        ),
        migrations.AlterField(
            model_name="llmserviceconfig",
            name="provider_config",
            field=models.ForeignKey(
                help_text="使用するLLMプロバイダー設定を選択",
                on_delete=django.db.models.deletion.PROTECT,
                to="llm_config.llmproviderconfig",
                verbose_name="LLM設定",
            ),
        ),
    ]
