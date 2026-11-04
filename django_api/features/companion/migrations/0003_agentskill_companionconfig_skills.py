"""Agent Skills（AgentSkill）を足し、Companion 設定から選べるようにする（スキーマだけ）.

旧 CompanionSkill の行は 0004 で AgentSkill に写し、0005 で旧モデルを消す。

旧 CompanionSkill.config の逆参照の名前（skills）は、設定に足す M2M（skills）と同じなので、
先に逆参照を外す。外さないと、この後の履歴のモデルで `config.skills` が旧スキルの逆参照に
なり、0004 で M2M に紐づけられない。逆参照の名前は DB を変えない。
"""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import features.companion.models


class Migration(migrations.Migration):
    dependencies = [
        ("companion", "0002_rename_persona_prompt_ref_to_system_prompt_ref"),
    ]

    operations = [
        migrations.AlterField(
            model_name="companionskill",
            name="config",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="companion.companionconfig",
                verbose_name="Companion 設定",
            ),
        ),
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
                            features.companion.models.validate_skill_name_not_reserved,
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
            },
        ),
        migrations.AddField(
            model_name="companionconfig",
            name="skills",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "この設定で使うスキル（Agent Skills に登録したもの）。"
                    "無効にしたスキルは、選んでいても使わない"
                ),
                related_name="configs",
                to="companion.agentskill",
                verbose_name="スキル",
            ),
        ),
    ]
