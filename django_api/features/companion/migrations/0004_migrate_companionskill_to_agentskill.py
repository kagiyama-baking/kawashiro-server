"""旧 CompanionSkill を AgentSkill に写し、元の設定で選んだ状態にする（データだけ）.

AgentSkill の本文は、Langfuse の text プロンプト `companion-skill-<スキル名>` をスキルの
ラベルで取る（フォールバックはない）。写すのは名前・説明・有効と、本文の参照のラベル。

次のどれかが 1 件でもあれば、何も写さずに RuntimeError で止める（起動時の migrate が
止まる）。黙って写すと、別の本文を読んだり、どちらかの内容を捨てたりするため。
- 本文の参照の Langfuse プロンプト名が `companion-skill-<スキル名>` でない
- 同じ名前の旧スキルの内容（説明・有効・ラベル）が、設定ごとに違う（名前は全体で一意になる）

旧スキルの本文の参照（LangfusePromptRef）は消さない（戻すときに使い直す）。

戻すときは、各設定で選んでいるスキルを旧スキルとして作り直す（0005 の前で旧スキルの行が
残っていれば、その行を更新する）。本文の参照は識別名 `companion-skill-<スキル名>` で探し、
なければ作る。見つかった参照が別の本文を読む（Langfuse プロンプト名かラベルがスキルと違う）
なら、何も戻さずに RuntimeError で止める（行きと同じく、黙って別の本文を読ませない）。
どの設定でも選んでいないスキルは戻らない。
"""

from django.db import migrations

# features.companion.models.SKILL_PROMPT_NAME_PREFIX と同じ（migration はモデルのコードに依らない）
SKILL_PROMPT_NAME_PREFIX = "companion-skill-"
ROLLBACK_REF_DESCRIPTION = "Companion スキルの本文（ロールバックで再作成）"


def _prompt_name(skill_name: str) -> str:
    """スキルの本文を置く Langfuse のプロンプト名."""
    return f"{SKILL_PROMPT_NAME_PREFIX}{skill_name}"


def _naming_problems(legacy_skills) -> list[str]:
    """本文の参照の Langfuse プロンプト名が規則どおりでない旧スキルを挙げる."""
    return [
        (
            f"スキル「{skill.name}」（設定「{skill.config.name}」）: 本文の参照"
            f"「{skill.prompt_ref.name}」の Langfuse プロンプト名が"
            f"「{skill.prompt_ref.langfuse_prompt_name}」で、"
            f"「{_prompt_name(skill.name)}」ではありません"
        )
        for skill in legacy_skills
        if skill.prompt_ref.langfuse_prompt_name != _prompt_name(skill.name)
    ]


def _conflict_problems(legacy_skills) -> list[str]:
    """同じ名前で、設定ごとに内容（説明・有効・ラベル）が違う旧スキルを挙げる."""
    by_name = {}
    for skill in legacy_skills:
        by_name.setdefault(skill.name, []).append(skill)
    return [
        (
            f"スキル「{name}」: 設定"
            + "・".join(f"「{skill.config.name}」" for skill in skills)
            + "で、説明・有効・ラベルのどれかが違います"
        )
        for name, skills in by_name.items()
        if len(
            {
                (skill.description, skill.is_enabled, skill.prompt_ref.label)
                for skill in skills
            }
        )
        > 1
    ]


def migrate_forward(apps, schema_editor):
    """旧スキルを AgentSkill に写し、元の設定で選ぶ（規則に合わなければ止める）."""
    CompanionSkill = apps.get_model("companion", "CompanionSkill")
    AgentSkill = apps.get_model("companion", "AgentSkill")

    legacy_skills = list(
        CompanionSkill.objects.select_related("config", "prompt_ref").order_by(
            "name", "config__name"
        )
    )
    problems = _naming_problems(legacy_skills) + _conflict_problems(legacy_skills)
    if problems:
        raise RuntimeError(
            "旧 Companion スキルを Agent Skills に写せないので、migration を止めました"
            "（何も変えていません）。スキルの本文は Langfuse の text プロンプト"
            f"「{SKILL_PROMPT_NAME_PREFIX}<スキル名>」から読むようになり、スキル名は"
            "全体で一意になります。次を直してから migrate し直してください:\n"
            + "\n".join(f"- {problem}" for problem in problems)
        )

    for legacy in legacy_skills:
        skill, _ = AgentSkill.objects.get_or_create(
            name=legacy.name,
            defaults={
                "description": legacy.description,
                "label": legacy.prompt_ref.label,
                "is_enabled": legacy.is_enabled,
            },
        )
        legacy.config.skills.add(skill)


def _rollback_ref_problems(skills, refs_by_name) -> list[str]:
    """戻すと、スキルと別の本文を読む旧スキルになるスキルを挙げる.

    規則どおりの識別名の参照があり、その Langfuse プロンプト名かラベルがスキルと違うとき。
    """
    problems = []
    for skill in skills:
        prompt_name = _prompt_name(skill.name)
        ref = refs_by_name.get(prompt_name)
        if ref is None or (ref.langfuse_prompt_name, ref.label) == (
            prompt_name,
            skill.label,
        ):
            continue
        problems.append(
            f"スキル「{skill.name}」: 参照「{ref.name}」は"
            f"「{ref.langfuse_prompt_name}@{ref.label}」を読みますが、スキルの本文は"
            f"「{prompt_name}@{skill.label}」です"
        )
    return problems


def migrate_backward(apps, schema_editor):
    """各設定で選んでいるスキルを、本文の参照ごと旧スキルに戻す（別の本文を読むなら止める）."""
    CompanionConfig = apps.get_model("companion", "CompanionConfig")
    CompanionSkill = apps.get_model("companion", "CompanionSkill")
    LangfusePromptRef = apps.get_model("langfuse_integration", "LangfusePromptRef")

    selections = [
        (config, skill)
        for config in CompanionConfig.objects.prefetch_related("skills").order_by(
            "name"
        )
        for skill in config.skills.all()
    ]
    skills = sorted(
        {skill.pk: skill for _, skill in selections}.values(),
        key=lambda skill: skill.name,
    )
    refs_by_name = LangfusePromptRef.objects.in_bulk(
        [_prompt_name(skill.name) for skill in skills], field_name="name"
    )
    problems = _rollback_ref_problems(skills, refs_by_name)
    if problems:
        raise RuntimeError(
            "Agent Skills を旧 Companion スキルに戻すと、スキルと別の本文を読むので、"
            "migration を止めました（何も変えていません）。次の参照の Langfuse "
            "プロンプト名・ラベルをスキルに合わせるか、参照を消してから戻し直して"
            "ください:\n" + "\n".join(f"- {problem}" for problem in problems)
        )

    for config, skill in selections:
        prompt_name = _prompt_name(skill.name)
        prompt_ref, _ = LangfusePromptRef.objects.get_or_create(
            name=prompt_name,
            defaults={
                "langfuse_prompt_name": prompt_name,
                "label": skill.label,
                "description": ROLLBACK_REF_DESCRIPTION,
            },
        )
        CompanionSkill.objects.update_or_create(
            config=config,
            name=skill.name,
            defaults={
                "description": skill.description,
                "is_enabled": skill.is_enabled,
                "prompt_ref": prompt_ref,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("companion", "0003_agentskill_companionconfig_skills"),
    ]

    operations = [
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
