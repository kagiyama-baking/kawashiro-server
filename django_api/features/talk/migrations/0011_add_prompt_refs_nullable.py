"""TalkConfig にプロンプト参照 FK を nullable で追加する."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("talk", "0010_rename_app_generate_to_talk"),
        ("langfuse_integration", "0002_seed_default_refs"),
    ]

    operations = [
        migrations.AddField(
            model_name="talkconfig",
            name="system_prompt_ref",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="システムプロンプト",
                help_text="システムプロンプトの Langfuse参照",
            ),
        ),
        migrations.AddField(
            model_name="talkconfig",
            name="user_prompt_ref",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="ユーザープロンプト",
                help_text="ユーザープロンプトテンプレートの Langfuse参照",
            ),
        ),
    ]
