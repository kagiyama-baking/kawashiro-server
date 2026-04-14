"""HNAgentConfig の Devil's Advocate / Security Responder FK を required (null=False) 化する."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hn_agent", "0016_populate_new_agent_prompt_refs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="hnagentconfig",
            name="devils_advocate_system_prompt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Devil's Advocate システムプロンプト",
                help_text="Devil's Advocate に与えるシステムプロンプト（Langfuse参照）",
            ),
        ),
        migrations.AlterField(
            model_name="hnagentconfig",
            name="devils_advocate_user_prompt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Devil's Advocate ユーザープロンプト",
                help_text="Devil's Advocate に与えるユーザープロンプト（Langfuse参照）",
            ),
        ),
        migrations.AlterField(
            model_name="hnagentconfig",
            name="security_responder_system_prompt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Security Responder システムプロンプト",
                help_text="Security Responder に与えるシステムプロンプト（Langfuse参照）",
            ),
        ),
        migrations.AlterField(
            model_name="hnagentconfig",
            name="security_responder_user_prompt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Security Responder ユーザープロンプト",
                help_text="Security Responder に与えるユーザープロンプト（Langfuse参照）",
            ),
        ),
    ]
