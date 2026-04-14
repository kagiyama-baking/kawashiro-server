"""HNAgentConfig に Devil's Advocate / Security Responder プロンプト参照 FK を nullable で追加する."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hn_agent", "0014_hnagentconfig_front_page_limit"),
        ("langfuse_integration", "0003_seed_new_agent_refs"),
    ]

    operations = [
        migrations.AddField(
            model_name="hnagentconfig",
            name="devils_advocate_system_prompt",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Devil's Advocate システムプロンプト",
                help_text="Devil's Advocate に与えるシステムプロンプト（Langfuse参照）",
            ),
        ),
        migrations.AddField(
            model_name="hnagentconfig",
            name="devils_advocate_user_prompt",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Devil's Advocate ユーザープロンプト",
                help_text="Devil's Advocate に与えるユーザープロンプト（Langfuse参照）",
            ),
        ),
        migrations.AddField(
            model_name="hnagentconfig",
            name="security_responder_system_prompt",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Security Responder システムプロンプト",
                help_text="Security Responder に与えるシステムプロンプト（Langfuse参照）",
            ),
        ),
        migrations.AddField(
            model_name="hnagentconfig",
            name="security_responder_user_prompt",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="Security Responder ユーザープロンプト",
                help_text="Security Responder に与えるユーザープロンプト（Langfuse参照）",
            ),
        ),
    ]
