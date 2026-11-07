"""Agent Skills（AgentSkill）を llm_config へ移す（状態だけ。DB は変えない）.

llm_config の 0014 が同じ表（companion_agentskill）で AgentSkill を作った後に、設定の選択
（skills）の向き先をそちらに替え、companion 側のモデルを状態から消す。選択の中間表
（companion_companionconfig_skills）の名前と列（agentskill_id）は、設定のモデルと参照先の
モデル名から決まるので変わらない。

戻すときは `migrate llm_config 0013`（この 0006 も外れる）。`migrate companion 0005` だけ
では llm_config の 0014 が当たったまま残り、内容の型（ContentType）の行も llm_config のまま
になる（古い版の管理画面では、それまでの履歴と付けた権限が見えない）。
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companion", "0005_delete_companionskill"),
        ("llm_config", "0014_move_agentskill_from_companion"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="companionconfig",
                    name="skills",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "この設定で使うスキル（Agent Skills に登録したもの）。"
                            "無効にしたスキルは、選んでいても使わない"
                        ),
                        related_name="configs",
                        to="llm_config.agentskill",
                        verbose_name="スキル",
                    ),
                ),
                migrations.DeleteModel(
                    name="AgentSkill",
                ),
            ],
            database_operations=[],
        ),
    ]
