"""HNAgentConfig に Langfuse プロンプト参照 FK を nullable で追加する."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hn_agent", "0010_remove_investigation"),
        ("langfuse_integration", "0002_seed_default_refs"),
    ]

    operations = [
        migrations.AddField(
            model_name="hnagentconfig",
            name="orchestrator_system_prompt",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Orchestrator システムプロンプト",
                help_text="Orchestrator に与えるシステムプロンプト（Langfuse参照）",
            ),
        ),
        migrations.AddField(
            model_name="hnagentconfig",
            name="orchestrator_user_prompt",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Orchestrator ユーザープロンプト",
                help_text="Orchestrator に与えるユーザープロンプト（Langfuse参照）",
            ),
        ),
        migrations.AddField(
            model_name="hnagentconfig",
            name="detective_system_prompt",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Detective システムプロンプト",
                help_text="Detective に与えるシステムプロンプト（Langfuse参照）",
            ),
        ),
        migrations.AddField(
            model_name="hnagentconfig",
            name="detective_user_prompt",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Detective ユーザープロンプト",
                help_text="Detective に与えるユーザープロンプト（Langfuse参照）",
            ),
        ),
    ]
