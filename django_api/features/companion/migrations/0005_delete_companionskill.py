"""旧 CompanionSkill を消す（行は 0004 で AgentSkill に写してある）.

戻すと空の表ができ、0004 を戻したときに各設定で選んでいるスキルから行を作り直す。
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("companion", "0004_migrate_companionskill_to_agentskill"),
    ]

    operations = [
        migrations.DeleteModel(
            name="CompanionSkill",
        ),
    ]
