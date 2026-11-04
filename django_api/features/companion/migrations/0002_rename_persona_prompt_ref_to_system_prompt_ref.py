"""CompanionConfig.persona_prompt_ref を system_prompt_ref に改名し、表示を変える.

手書きの migration。makemigrations は改名かどうかを対話で確かめ、対話なしでは改名と
みなさない（列の削除と追加として扱うので、既存の設定の参照先が失われる）。RenameField で
列の名前だけを変え、参照先（FK・PROTECT・related_name）はそのまま残す。表示
（verbose_name・help_text）の変更は DB を変えない。
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companion", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="companionconfig",
            old_name="persona_prompt_ref",
            new_name="system_prompt_ref",
        ),
        migrations.AlterField(
            model_name="companionconfig",
            name="system_prompt_ref",
            field=models.ForeignKey(
                help_text="全スキルに共通のシステムプロンプトの Langfuse参照",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="langfuse_integration.langfusepromptref",
                verbose_name="システムプロンプト",
            ),
        ),
    ]
