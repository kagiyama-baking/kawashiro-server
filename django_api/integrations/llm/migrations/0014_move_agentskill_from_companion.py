"""Agent Skills（AgentSkill）を companion から llm_config へ移す（状態だけ。DB は変えない）.

表は companion の 0003 が作った companion_agentskill をそのまま使う（db_table）。この後の
companion の 0006 が、設定の選択（CompanionConfig.skills）の向き先をこのモデルに替え、
companion 側のモデルを状態から消す。どちらも DB を変えないので、行・選択・表は残る。

戻すときは `migrate llm_config 0013`（companion の 0006 も外れ、AgentSkill は companion の
モデルに戻る）。
"""

import django.core.validators
from django.db import migrations, models

import integrations.llm.models


class Migration(migrations.Migration):
    dependencies = [
        ("llm_config", "0013_add_companion_service_choice"),
        ("companion", "0005_delete_companionskill"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="AgentSkill",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "name",
                            models.CharField(
                                help_text=(
                                    "英小文字・数字・ハイフン（例: good-morning）、64 字以内。"
                                    "先頭・末尾・連続のハイフンは使えない。本文は、名前の前に "
                                    "companion-skill- を付けた Langfuse の text プロンプト"
                                    "（例: companion-skill-good-morning）から読むので、"
                                    "名前を変えると本文を読む先も変わる"
                                ),
                                max_length=64,
                                unique=True,
                                validators=[
                                    django.core.validators.RegexValidator(
                                        message=(
                                            "スキル名は英小文字・数字をハイフンでつないだ形で"
                                            "入力してください（例: good-morning）"
                                        ),
                                        regex="^[a-z0-9]+(-[a-z0-9]+)*\\Z",
                                    ),
                                    integrations.llm.models.validate_skill_name_not_reserved,
                                ],
                                verbose_name="スキル名",
                            ),
                        ),
                        (
                            "description",
                            models.CharField(
                                help_text=(
                                    "どんな発話のときに使うスキルか（例: 朝のあいさつ。"
                                    "「おはよう」など）。モデルはこの説明を読んで使うスキルを選ぶ。"
                                    "1024 字以内"
                                ),
                                max_length=1024,
                                verbose_name="説明",
                            ),
                        ),
                        (
                            "label",
                            models.CharField(
                                default="production",
                                help_text=(
                                    "本文を取る Langfuse のプロンプトのラベル"
                                    "（staging / production）"
                                ),
                                max_length=50,
                                verbose_name="ラベル",
                            ),
                        ),
                        (
                            "is_enabled",
                            models.BooleanField(
                                default=True,
                                help_text="無効にしたスキルは、設定で選んでいても使わない",
                                verbose_name="有効",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Agent Skill",
                        "verbose_name_plural": "Agent Skills",
                        "ordering": ["name"],
                        "db_table": "companion_agentskill",
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
