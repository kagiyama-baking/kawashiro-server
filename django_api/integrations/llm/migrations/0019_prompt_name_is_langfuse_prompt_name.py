"""プロンプト（Prompt）の名前を、本文を取る Langfuse のプロンプト名そのものにする.

0018 までは、Django 側の識別名（`name`）と Langfuse のプロンプト名（`langfuse_prompt_name`）を
別に持ち、Langfuse から取れなければフォールバックテキスト（`fallback_text`）を使っていた。
前進では、名前を 200 字までにしてから、名前が Langfuse のプロンプト名と違う行の名前を
Langfuse のプロンプト名に付け替え（本文を取る先は変わらない）、Langfuse のプロンプト名と
フォールバックテキストの列を消す。付け替えは 2 段で行う（いったん一時の名前
`__llm_config_0019__/<pk>` にしてから Langfuse のプロンプト名にする）ので、名前が入れ替わる行や、
ほかの行の Langfuse のプロンプト名を名前に持つ行があっても、一意の制約に触れない。

付け替える前に、0018 の最初と同じ検査をする（0018 の後に行が変わっていても止まるように）。
Langfuse のプロンプト名が名前にできない（空・前後の空白や改行・途中の改行・200 字超）、
ほかの行と重なる、名前か Langfuse のプロンプト名が一時の名前で始まる行が 1 件でもあれば、
何も変えずに RuntimeError で止める（起動時の migrate が止まる）。

後退では列を戻し（Langfuse のプロンプト名は名前と同じ、フォールバックテキストは空）、
HN Agent の system プロンプト 4 本の名前を、seed（langfuse_integration の 0002・0003）の識別名に
戻す（その識別名がほかの行に使われていなければ）。0018 までの名前は 100 字までなので、
100 字を超える名前の行が 1 件でもあれば、何も変えずに RuntimeError で止める。消した
フォールバックテキストと、seed 以外の元の識別名は戻らない。
"""

import re
from collections import defaultdict

import django.core.validators
from django.db import migrations, models
from django.db.models import F

# 名前の規則（integrations.llm.models.PROMPT_NAME_PATTERN と同じ。migration はモデルのコードに
# 依らないので、ここに持つ）と、名前の上限（0018 まで・この後）
PROMPT_NAME_PATTERN = r"^\S(?:.*\S)?\Z"
OLD_NAME_MAX_LENGTH = 100
NAME_MAX_LENGTH = 200
# 付け替えの途中に使う一時の名前の接頭辞
TEMPORARY_PREFIX = "__llm_config_0019__/"
# HN Agent の seed の system プロンプト（Langfuse のプロンプト名 → 0018 までの識別名）
HN_SEED_OLD_NAMES = {
    "hn-agent-orchestrator": "hn-agent-orchestrator-system",
    "hn-agent-detective": "hn-agent-detective-system",
    "hn-agent-devils-advocate": "hn-agent-devils-advocate-system",
    "hn-agent-security-responder": "hn-agent-security-responder-system",
}


def _name_problem(langfuse_prompt_name: str) -> str | None:
    """Langfuse のプロンプト名を名前にできない理由（できるなら None）."""
    if not langfuse_prompt_name.strip():
        return "Langfuse のプロンプト名が空です"
    if len(langfuse_prompt_name) > NAME_MAX_LENGTH:
        return f"Langfuse のプロンプト名が {NAME_MAX_LENGTH} 字を超えます"
    if not re.match(PROMPT_NAME_PATTERN, langfuse_prompt_name):
        return "Langfuse のプロンプト名の前後か途中に、空白か改行があります"
    return None


def _problems(rows) -> list[str]:
    """名前を Langfuse のプロンプト名にできない行（0018 の _problems と同じ検査）.

    Args:
        rows: (識別名, Langfuse のプロンプト名, ラベル) の並び

    Returns:
        直すべき行の説明（なければ空）
    """
    problems = []
    by_langfuse_name = defaultdict(list)
    for name, langfuse_name, label in rows:
        by_langfuse_name[langfuse_name].append((name, label))
        reason = _name_problem(langfuse_name)
        if reason is not None:
            problems.append(f"- {name}（{langfuse_name!r}@{label}）: {reason}")
        if name.startswith(TEMPORARY_PREFIX) or langfuse_name.startswith(
            TEMPORARY_PREFIX
        ):
            problems.append(
                f"- {name}（{langfuse_name}@{label}）: 名前か Langfuse のプロンプト名が、"
                f"移行の一時の名前（{TEMPORARY_PREFIX}）で始まります"
            )
    for langfuse_name, refs in sorted(by_langfuse_name.items()):
        if len(refs) > 1:
            problems.append(
                f"- Langfuse のプロンプト名 {langfuse_name} が重なっています: "
                + "、".join(
                    f"{name}（{langfuse_name}@{label}）" for name, label in refs
                )
            )
    return problems


def _stop_if_problems(rows) -> None:
    """名前にできない行があれば、何も変えずに RuntimeError で止める（0018 と同じ文面）."""
    problems = _problems(rows)
    if problems:
        raise RuntimeError(
            "プロンプトの名前を Langfuse のプロンプト名にできない参照があるので、migration を"
            "止めました（この migration は何も変えていません）。プロンプト（AI設定 → Prompts）の"
            "名前は Langfuse のプロンプト名そのものになり、一意です。この版より前のコードの"
            "管理画面（「Langfuse → Langfuseプロンプト参照」）か shell で、次の参照の Langfuse の"
            "プロンプト名を直すか、使っていない参照を消してから、migrate し直してください:\n"
            + "\n".join(problems)
        )


def rename_to_langfuse_prompt_names(apps, schema_editor):
    """名前を Langfuse のプロンプト名に付け替える（できない行があれば、何も変えずに止める）."""
    Prompt = apps.get_model("llm_config", "Prompt")
    prompts = Prompt.objects.using(schema_editor.connection.alias)
    rows = list(
        prompts.order_by("name").values_list(
            "pk", "name", "langfuse_prompt_name", "label"
        )
    )
    _stop_if_problems(
        [(name, langfuse_name, label) for _, name, langfuse_name, label in rows]
    )
    renamed = [
        (pk, langfuse_name)
        for pk, name, langfuse_name, _ in rows
        if name != langfuse_name
    ]
    # 1 段目で一時の名前にしてから、2 段目で Langfuse のプロンプト名にする
    for pk, _ in renamed:
        prompts.filter(pk=pk).update(name=f"{TEMPORARY_PREFIX}{pk}")
    for pk, langfuse_name in renamed:
        prompts.filter(pk=pk).update(name=langfuse_name)


def restore_langfuse_prompt_names(apps, schema_editor):
    """Langfuse のプロンプト名を名前と同じにし、HN Agent の seed の識別名を戻す.

    100 字を超える名前があれば、何も変えずに止める（0018 までの名前は 100 字まで）。
    """
    Prompt = apps.get_model("llm_config", "Prompt")
    prompts = Prompt.objects.using(schema_editor.connection.alias)
    names = set(prompts.values_list("name", flat=True))
    too_long = sorted(name for name in names if len(name) > OLD_NAME_MAX_LENGTH)
    if too_long:
        raise RuntimeError(
            f"{OLD_NAME_MAX_LENGTH} 字を超えるプロンプト名があるので、戻すのを止めました"
            "（何も変えていません）。0018 までの名前は 100 字までです。次のプロンプトの名前を、"
            "Langfuse のプロンプト名ごと 100 字以内にしてから、戻し直してください:\n"
            + "\n".join(f"- {name}（{len(name)} 字）" for name in too_long)
        )
    prompts.update(langfuse_prompt_name=F("name"))
    for langfuse_name, old_name in HN_SEED_OLD_NAMES.items():
        if old_name not in names:
            prompts.filter(name=langfuse_name).update(name=old_name)


class Migration(migrations.Migration):
    dependencies = [
        ("llm_config", "0018_move_prompt_from_langfuse_integration"),
        ("langfuse_integration", "0004_delete_langfusepromptref"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prompt",
            name="name",
            field=models.CharField(
                help_text=(
                    "本文を取る Langfuse の text プロンプトの名前そのもの"
                    "（例: hn-agent-orchestrator。フォルダは / で区切る）。200 字以内。"
                    "前後の空白と改行は使えない。名前を変えると本文を取る先も変わる"
                ),
                max_length=200,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message=(
                            "プロンプト名の前後には、空白と改行を入れられません"
                            "（途中の改行も不可）"
                        ),
                        regex="^\\S(?:.*\\S)?\\Z",
                    )
                ],
                verbose_name="プロンプト名",
            ),
        ),
        migrations.RunPython(
            rename_to_langfuse_prompt_names, restore_langfuse_prompt_names
        ),
        # 後退で列を足し直すときに、既存の行を埋める値（NOT NULL の列なので）
        migrations.AlterField(
            model_name="prompt",
            name="langfuse_prompt_name",
            field=models.CharField(
                default="",
                help_text="Langfuse 上で登録されているプロンプト名",
                max_length=200,
                verbose_name="Langfuseプロンプト名",
            ),
        ),
        migrations.RemoveField(model_name="prompt", name="langfuse_prompt_name"),
        migrations.RemoveField(model_name="prompt", name="fallback_text"),
        migrations.AlterField(
            model_name="prompt",
            name="label",
            field=models.CharField(
                default="production",
                help_text=(
                    "本文を取る Langfuse のプロンプトのラベル（staging / production）"
                ),
                max_length=50,
                verbose_name="ラベル",
            ),
        ),
        migrations.AlterField(
            model_name="prompt",
            name="description",
            field=models.CharField(
                blank=True,
                default="",
                help_text="このプロンプトの用途（admin の一覧に出る）",
                max_length=255,
                verbose_name="説明",
            ),
        ),
    ]
