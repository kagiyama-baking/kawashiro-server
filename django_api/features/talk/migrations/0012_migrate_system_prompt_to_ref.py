"""既存 TalkConfig.system_prompt TextField を LangfusePromptRef へ移行する.

各 TalkConfig ごとに以下を作成:
- talk-{name}-system: fallback_text に既存 system_prompt を保存
- talk-{name}-user: fallback_text は空（運用者が Langfuse で登録する想定）
"""

from django.db import migrations


def migrate_forward(apps, schema_editor):
    """既存 system_prompt を LangfusePromptRef の fallback_text に移管."""
    TalkConfig = apps.get_model("talk", "TalkConfig")
    LangfusePromptRef = apps.get_model("langfuse_integration", "LangfusePromptRef")

    for config in TalkConfig.objects.all():
        system_name = f"talk-{config.name}-system"
        user_name = f"talk-{config.name}-user"

        system_ref, _ = LangfusePromptRef.objects.update_or_create(
            name=system_name,
            defaults={
                "langfuse_prompt_name": system_name,
                "label": "production",
                "fallback_text": config.system_prompt or "",
                "description": f"Talk {config.name} のシステムプロンプト（自動移行）",
            },
        )
        user_ref, _ = LangfusePromptRef.objects.update_or_create(
            name=user_name,
            defaults={
                "langfuse_prompt_name": user_name,
                "label": "production",
                "fallback_text": "",
                "description": f"Talk {config.name} のユーザープロンプト（要 Langfuse 登録）",
            },
        )

        config.system_prompt_ref = system_ref
        config.user_prompt_ref = user_ref
        config.save(update_fields=["system_prompt_ref", "user_prompt_ref"])


def migrate_backward(apps, schema_editor):
    """ref の fallback_text から system_prompt TextField に戻す."""
    TalkConfig = apps.get_model("talk", "TalkConfig")
    for config in TalkConfig.objects.all():
        if config.system_prompt_ref_id:
            config.system_prompt = config.system_prompt_ref.fallback_text
            config.save(update_fields=["system_prompt"])


class Migration(migrations.Migration):

    dependencies = [
        ("talk", "0011_add_prompt_refs_nullable"),
        ("langfuse_integration", "0002_seed_default_refs"),
    ]

    operations = [
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
