"""プロンプト参照（LangfusePromptRef）を状態から消す（表は llm_config の Prompt が使い続ける）.

llm_config の 0018 が同じ表（langfuse_integration_langfusepromptref）で Prompt を作り、
hn_agent の 0018・companion の 0008・talk の 0020 が設定の外部キーの向き先をそちらに替えた後に、
古いモデルを状態から消す。表は消さない（DB は変えない）。

langfuse_integration のアプリはモデルを持たなくなる（admin のグループも出ない）が、
これまでの migration（0001〜0003。hn_agent・companion・talk の migration が依存する）の
ために INSTALLED_APPS に残す。

戻すときは `migrate llm_config 0017`（この 0004 も外れる）。
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("langfuse_integration", "0003_seed_new_agent_refs"),
        ("hn_agent", "0018_prompt_fks_to_llm_config"),
        ("companion", "0008_rename_system_prompt_ref_to_system_prompt"),
        ("talk", "0020_rename_system_prompt_ref_to_system_prompt"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="LangfusePromptRef"),
            ],
            database_operations=[],
        ),
    ]
