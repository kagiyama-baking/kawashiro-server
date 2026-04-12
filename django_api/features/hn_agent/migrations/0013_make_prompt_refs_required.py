"""HNAgentConfig のプロンプト参照 FK を required (null=False) 化する."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hn_agent", "0012_populate_prompt_refs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="hnagentconfig",
            name="orchestrator_system_prompt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Orchestrator システムプロンプト",
                help_text="Orchestrator に与えるシステムプロンプト（Langfuse参照）",
            ),
        ),
        migrations.AlterField(
            model_name="hnagentconfig",
            name="orchestrator_user_prompt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Orchestrator ユーザープロンプト",
                help_text="Orchestrator に与えるユーザープロンプト（Langfuse参照）",
            ),
        ),
        migrations.AlterField(
            model_name="hnagentconfig",
            name="detective_system_prompt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Detective システムプロンプト",
                help_text="Detective に与えるシステムプロンプト（Langfuse参照）",
            ),
        ),
        migrations.AlterField(
            model_name="hnagentconfig",
            name="detective_user_prompt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Detective ユーザープロンプト",
                help_text="Detective に与えるユーザープロンプト（Langfuse参照）",
            ),
        ),
    ]
