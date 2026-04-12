"""既存の HNAgentConfig 行にシード投入済みの LangfusePromptRef をバインドする."""

from django.db import migrations

PROMPT_NAME_MAP = {
    "orchestrator_system_prompt": "hn-agent-orchestrator-system",
    "orchestrator_user_prompt": "hn-agent-orchestrator-user",
    "detective_system_prompt": "hn-agent-detective-system",
    "detective_user_prompt": "hn-agent-detective-user",
}


def populate_forward(apps, schema_editor):
    """既存行にシード参照をバインド."""
    HNAgentConfig = apps.get_model("hn_agent", "HNAgentConfig")
    LangfusePromptRef = apps.get_model("langfuse_integration", "LangfusePromptRef")

    refs = {
        ref.name: ref
        for ref in LangfusePromptRef.objects.filter(name__in=PROMPT_NAME_MAP.values())
    }

    # 4種のシードが揃っていない場合は安全に中断
    missing = set(PROMPT_NAME_MAP.values()) - set(refs.keys())
    if missing:
        raise RuntimeError(
            f"LangfusePromptRef のシードが不足しています: {missing}。"
            "langfuse_integration.0002_seed_default_refs が適用されているか確認してください。"
        )

    for config in HNAgentConfig.objects.all():
        for field, ref_name in PROMPT_NAME_MAP.items():
            setattr(config, field, refs[ref_name])
        config.save(
            update_fields=list(PROMPT_NAME_MAP.keys()),
        )


def populate_backward(apps, schema_editor):
    """既存行の FK を None に戻す."""
    HNAgentConfig = apps.get_model("hn_agent", "HNAgentConfig")
    for config in HNAgentConfig.objects.all():
        for field in PROMPT_NAME_MAP:
            setattr(config, field, None)
        config.save(update_fields=list(PROMPT_NAME_MAP.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ("hn_agent", "0011_add_prompt_refs_nullable"),
        ("langfuse_integration", "0002_seed_default_refs"),
    ]

    operations = [
        migrations.RunPython(populate_forward, populate_backward),
    ]
