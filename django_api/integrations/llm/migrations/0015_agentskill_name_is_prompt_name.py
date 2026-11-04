"""Agent Skills のスキル名を、本文を読む Langfuse のプロンプト名そのものにする.

0014 までは、本文を Langfuse の text プロンプト `companion-skill-<スキル名>` から読んでいた。
読む先を変えないよう、前進では、いまある全部の行の名前に接頭辞 `companion-skill-` を付ける
（Langfuse 側は変えない）。付け替えは名前の長い順に行う（付けた名前が、まだ付け替えていない
ほかの行の名前と重ならないように）。接頭辞を付けると 64 字（名前の上限）を超える行が 1 件でも
あれば、何も変えずに RuntimeError で止める（起動時の migrate が止まる）。

後退では、接頭辞の付いた行の名前からだけ外す（名前の短い順）。接頭辞のない行（0015 の後に
登録したスキル）は変えないので、戻した後は `companion-skill-<名前>` を読むようになる。外した
名前のスキルがすでにあるか、外した名前が予約した名前（`instrumentation`）なら、何も変えずに
RuntimeError で止める。
"""

import django.core.validators
from django.db import migrations, models

import integrations.llm.models

# 0015 より前の、本文のプロンプト名の接頭辞（migration はモデルのコードに依らないので、ここに持つ）
PROMPT_NAME_PREFIX = "companion-skill-"
# スキル名の上限（AgentSkill.name の max_length）
NAME_MAX_LENGTH = 64
# スキル名に使えない予約した名前（integrations.llm.models.RESERVED_SKILL_NAMES と同じ。
# migration はモデルのコードに依らないので、ここに持つ）
RESERVED_NAMES = frozenset({"instrumentation"})


def prefix_names(apps, schema_editor):
    """全部のスキル名に接頭辞を付ける（64 字を超える名前があれば、何も変えずに止める）."""
    AgentSkill = apps.get_model("llm_config", "AgentSkill")
    skills = sorted(
        AgentSkill.objects.values_list("pk", "name"),
        key=lambda skill: (-len(skill[1]), skill[1]),
    )
    too_long = [
        name for _, name in skills if len(PROMPT_NAME_PREFIX + name) > NAME_MAX_LENGTH
    ]
    if too_long:
        raise RuntimeError(
            "Agent Skills のスキル名に接頭辞 companion-skill- を付けると 64 字を超えるので、"
            "migration を止めました（何も変えていません）。スキル名は、本文を読む Langfuse の"
            "プロンプト名そのものになります（いまの本文は companion-skill-<スキル名> にあります）。"
            f"次のスキルの名前を {NAME_MAX_LENGTH - len(PROMPT_NAME_PREFIX)} 字以内にし、"
            "Langfuse のプロンプト名も companion-skill-<新しい名前> に合わせてから、"
            "migrate し直してください:\n"
            + "\n".join(f"- {name}（{len(name)} 字）" for name in too_long)
        )
    for pk, name in skills:
        AgentSkill.objects.filter(pk=pk).update(name=PROMPT_NAME_PREFIX + name)


def _strip_problem(stripped: str, unprefixed: set[str]) -> str | None:
    """接頭辞を外した名前を使えない理由（使えるなら None）.

    重なりうるのは、接頭辞のない名前（変えない行）だけ。接頭辞が 2 つ付いた名前を外すと
    1 つ付いた名前になるが、そちらは先に（短い順で）外している。
    """
    if stripped in unprefixed:
        return "同じ名前のスキルがあります"
    if stripped in RESERVED_NAMES:
        return "予約した名前です"
    return None


def strip_prefix(apps, schema_editor):
    """接頭辞の付いたスキル名から外す（外せない名前があれば、何も変えずに止める）."""
    AgentSkill = apps.get_model("llm_config", "AgentSkill")
    names = set(AgentSkill.objects.values_list("name", flat=True))
    prefixed = sorted(
        (name for name in names if name.startswith(PROMPT_NAME_PREFIX)),
        key=lambda name: (len(name), name),
    )
    unprefixed = names - set(prefixed)
    problems = []
    for name in prefixed:
        stripped = name.removeprefix(PROMPT_NAME_PREFIX)
        reason = _strip_problem(stripped, unprefixed)
        if reason is not None:
            problems.append(f"- {name} → {stripped}（{reason}）")
    if problems:
        raise RuntimeError(
            "Agent Skills のスキル名から接頭辞 companion-skill- を外せないスキルがあるので、"
            "migration を止めました（何も変えていません）。次のスキルの名前を変えてから、"
            "戻し直してください:\n" + "\n".join(problems)
        )
    for name in prefixed:
        AgentSkill.objects.filter(name=name).update(
            name=name.removeprefix(PROMPT_NAME_PREFIX)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("llm_config", "0014_move_agentskill_from_companion"),
        ("companion", "0006_move_agentskill_to_llm_config"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agentskill",
            name="name",
            field=models.CharField(
                help_text=(
                    "英小文字・数字・ハイフン（例: good-morning）、64 字以内。"
                    "先頭・末尾・連続のハイフンは使えない。名前は、本文を読む Langfuse の text "
                    "プロンプトの名前そのもの（版はラベルで選ぶ）なので、名前を変えると本文を読む先も"
                    "変わる"
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
        migrations.RunPython(prefix_names, strip_prefix),
    ]
