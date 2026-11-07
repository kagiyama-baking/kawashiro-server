"""HN Agent 設定の 8 本のプロンプトの外部キーを、llm_config の Prompt へ向ける（状態だけ）.

llm_config の 0018 が、langfuse_integration の LangfusePromptRef と同じ表で Prompt を作った後に、
向き先だけを替える。表も列も外部キー制約も同じ表を指したままなので、DB は変えない（状態だけの
AlterField。help_text も admin の表示だけ）。

戻すときは `migrate llm_config 0017`（この 0018 も外れる）。
"""

import django.db.models.deletion
from django.db import migrations, models

# (項目, 表示名, 説明)
PROMPT_FIELDS = [
    (
        "orchestrator_system_prompt",
        "Orchestrator システムプロンプト",
        "Orchestrator に与えるシステムプロンプト（AI設定 → Prompts）",
    ),
    (
        "orchestrator_user_prompt",
        "Orchestrator ユーザープロンプト",
        "Orchestrator に与えるユーザープロンプト（AI設定 → Prompts）",
    ),
    (
        "detective_system_prompt",
        "Detective システムプロンプト",
        "Detective に与えるシステムプロンプト（AI設定 → Prompts）",
    ),
    (
        "detective_user_prompt",
        "Detective ユーザープロンプト",
        "Detective に与えるユーザープロンプト（AI設定 → Prompts）",
    ),
    (
        "devils_advocate_system_prompt",
        "Devil's Advocate システムプロンプト",
        "Devil's Advocate に与えるシステムプロンプト（AI設定 → Prompts）",
    ),
    (
        "devils_advocate_user_prompt",
        "Devil's Advocate ユーザープロンプト",
        "Devil's Advocate に与えるユーザープロンプト（AI設定 → Prompts）",
    ),
    (
        "security_responder_system_prompt",
        "Security Responder システムプロンプト",
        "Security Responder に与えるシステムプロンプト（AI設定 → Prompts）",
    ),
    (
        "security_responder_user_prompt",
        "Security Responder ユーザープロンプト",
        "Security Responder に与えるユーザープロンプト（AI設定 → Prompts）",
    ),
]


class Migration(migrations.Migration):
    dependencies = [
        ("hn_agent", "0017_make_new_agent_prompt_refs_required"),
        ("llm_config", "0018_move_prompt_from_langfuse_integration"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="hnagentconfig",
                    name=name,
                    field=models.ForeignKey(
                        help_text=help_text,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="llm_config.prompt",
                        verbose_name=verbose_name,
                    ),
                )
                for name, verbose_name, help_text in PROMPT_FIELDS
            ],
            database_operations=[],
        ),
    ]
