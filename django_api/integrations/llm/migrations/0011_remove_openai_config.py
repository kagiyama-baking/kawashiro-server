"""OpenAIConfig モデルを削除する（LLMProviderConfig への移行完了により不要）."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("llm_config", "0010_rename_talk_to_talk_generator"),
    ]

    operations = [
        migrations.DeleteModel(
            name="OpenAIConfig",
        ),
    ]
