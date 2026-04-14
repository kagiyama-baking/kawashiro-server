"""既存の HNAgentConfig 行に新規エージェントのシード参照をバインドする."""

from django.db import migrations

PROMPT_NAME_MAP = {
    "devils_advocate_system_prompt": "hn-agent-devils-advocate-system",
    "devils_advocate_user_prompt": "hn-agent-devils-advocate-user",
    "security_responder_system_prompt": "hn-agent-security-responder-system",
    "security_responder_user_prompt": "hn-agent-security-responder-user",
}


def populate_forward(apps, schema_editor):
    """既存行に 4 件のシード参照をバインド."""
    HNAgentConfig = apps.get_model("hn_agent", "HNAgentConfig")
    LangfusePromptRef = apps.get_model("langfuse_integration", "LangfusePromptRef")

    refs = {
        ref.name: ref
        for ref in LangfusePromptRef.objects.filter(name__in=PROMPT_NAME_MAP.values())
    }

    missing = set(PROMPT_NAME_MAP.values()) - set(refs.keys())
    if missing:
        raise RuntimeError(
            f"LangfusePromptRef のシードが不足しています: {missing}。"
            "langfuse_integration.0003_seed_new_agent_refs が適用されているか確認してください。"
        )

    for config in HNAgentConfig.objects.all():
        for field, ref_name in PROMPT_NAME_MAP.items():
            setattr(config, field, refs[ref_name])
        config.save(update_fields=list(PROMPT_NAME_MAP.keys()))


def populate_backward(apps, schema_editor):
    """既存行の 4 FK を None に戻す."""
    HNAgentConfig = apps.get_model("hn_agent", "HNAgentConfig")
    for config in HNAgentConfig.objects.all():
        for field in PROMPT_NAME_MAP:
            setattr(config, field, None)
        config.save(update_fields=list(PROMPT_NAME_MAP.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ("hn_agent", "0015_add_new_agent_prompt_refs_nullable"),
        ("langfuse_integration", "0003_seed_new_agent_refs"),
    ]

    operations = [
        migrations.RunPython(populate_forward, populate_backward),
    ]
