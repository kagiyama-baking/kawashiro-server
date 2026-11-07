"""Companion 設定のシステムプロンプトを llm_config の Prompt へ向け、system_prompt に改名する.

llm_config の 0018 が langfuse_integration の LangfusePromptRef と同じ表で Prompt を作った後に、
まず外部キーの向き先だけを替え（状態だけ。同じ表を指すので DB は変えない）、続けて項目を
system_prompt_ref から system_prompt に改める（RenameField。列が system_prompt_ref_id から
system_prompt_id になり、外部キー制約も新しい列で作り直す）。選んだプロンプトはそのまま残る。

手書きの migration。makemigrations は改名かどうかを対話で確かめ、対話なしでは改名とみなさない
（列の削除と追加として扱うので、設定のシステムプロンプトの値が失われる）。

戻すときは `migrate llm_config 0017`（この 0008 も外れ、列は system_prompt_ref_id に戻る）。
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companion", "0007_alter_companionconfig_skills_related_name"),
        ("llm_config", "0018_move_prompt_from_langfuse_integration"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="companionconfig",
                    name="system_prompt_ref",
                    field=models.ForeignKey(
                        help_text="全スキルに共通のシステムプロンプト（AI設定 → Prompts）",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="llm_config.prompt",
                        verbose_name="システムプロンプト",
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.RenameField(
            model_name="companionconfig",
            old_name="system_prompt_ref",
            new_name="system_prompt",
        ),
    ]
