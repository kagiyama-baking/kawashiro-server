"""TalkConfig のプロンプト FK を required 化し、旧 system_prompt TextField を削除する."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("talk", "0012_migrate_system_prompt_to_ref"),
    ]

    operations = [
        migrations.AlterField(
            model_name="talkconfig",
            name="system_prompt_ref",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="システムプロンプト",
                help_text="システムプロンプトの Langfuse参照",
            ),
        ),
        migrations.AlterField(
            model_name="talkconfig",
            name="user_prompt_ref",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="ユーザープロンプト",
                help_text="ユーザープロンプトテンプレートの Langfuse参照",
            ),
        ),
        # ロールバック（reverse）時に復活するフィールドが NOT NULL だと
        # 既存行で IntegrityError になるため、一旦 null 許容へ変更してから削除する。
        migrations.AlterField(
            model_name="talkconfig",
            name="system_prompt",
            field=models.TextField(
                blank=True,
                null=True,
                default="",
                verbose_name="システムプロンプト",
            ),
        ),
        migrations.RemoveField(
            model_name="talkconfig",
            name="system_prompt",
        ),
    ]
