"""プロンプト（Langfuse プロンプト参照）を langfuse_integration から llm_config へ移す（表は変えない）.

langfuse_integration の LangfusePromptRef を、表（langfuse_integration_langfusepromptref）を
そのまま使う llm_config の Prompt にする（db_table）。この後の hn_agent の 0018・companion の
0008・talk の 0020 が、設定の外部キーの向き先をこのモデルに替え、langfuse_integration の 0004 が
古いモデルを状態から消す。表を変えないので、行と外部キーの値は残る。

権限と管理画面の履歴は内容の型（ContentType）の行を指すので、その行も
langfuse_integration/langfusepromptref から llm_config/prompt へ付け替える（id はそのままなので、
付けた権限も履歴も移したモデルで見える）。モデル名が変わるので、既定の権限の codename と表示名も
`<操作>_prompt`・`Can <操作> Prompt` に改める。元の行がなければ何もしない（新しい DB では、内容の型は
migrate の後に作られる）。移す先の行もあれば（戻した後の migrate が作った行など）、その行を指す
履歴と権限を元の行へ寄せてから消し、元の行を付け替える（行は 1 つにまとまる）。

最初に、続く llm_config の 0019 が名前を Langfuse のプロンプト名にできるかを検査する（0019 と
同じ検査）。Langfuse のプロンプト名が名前にできない（空・前後の空白や改行・途中の改行・200 字超）、
ほかの参照と重なる、名前か Langfuse のプロンプト名が 0019 の一時の名前で始まる参照が 1 件でも
あれば、何も変えずに RuntimeError で止める（この 0018 から 0019 まで、どれも当たらない）。

戻すときは `migrate llm_config 0017`（設定の付け替えと古いモデルの削除も外れ、プロンプトは
langfuse_integration のモデルに戻る。内容の型の行も同じ規則で戻す）。
"""

import re
from collections import defaultdict

from django.conf import settings
from django.db import migrations, models

# 内容の型（ContentType）の (app_label, model) と、既定の権限の表示名に使うモデルの表示名
OLD_CONTENT_TYPE = ("langfuse_integration", "langfusepromptref")
NEW_CONTENT_TYPE = ("llm_config", "prompt")
VERBOSE_NAMES = {OLD_CONTENT_TYPE: "Langfuseプロンプト参照", NEW_CONTENT_TYPE: "Prompt"}
# Django が作る既定の権限の操作（codename は `<操作>_<モデル名>`）
PERMISSION_ACTIONS = ("add", "change", "delete", "view")

# 0019 の名前の規則・名前の上限・一時の名前の接頭辞（migration はほかの migration とモデルの
# コードに依らないので、ここに持つ）
PROMPT_NAME_PATTERN = r"^\S(?:.*\S)?\Z"
NAME_MAX_LENGTH = 200
TEMPORARY_PREFIX = "__llm_config_0019__/"


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
    """名前を Langfuse のプロンプト名にできない参照（0019 の _problems と同じ検査）.

    Args:
        rows: (識別名, Langfuse のプロンプト名, ラベル) の並び

    Returns:
        直すべき参照の説明（なければ空）
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
    """名前にできない参照があれば、何も変えずに RuntimeError で止める（0019 と同じ文面）."""
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


def check_names_can_become_langfuse_prompt_names(apps, schema_editor):
    """0019 で名前を Langfuse のプロンプト名にできない参照があれば、何も変えずに止める."""
    LangfusePromptRef = apps.get_model("langfuse_integration", "LangfusePromptRef")
    _stop_if_problems(
        LangfusePromptRef.objects.using(schema_editor.connection.alias)
        .order_by("name")
        .values_list("name", "langfuse_prompt_name", "label")
    )


def _permission_holders(apps) -> list[tuple[type, str]]:
    """権限を付けられるもの（グループ・ユーザー）の中間表と、持ち主の列."""
    group = apps.get_model("auth", "Group")
    user = apps.get_model(settings.AUTH_USER_MODEL)
    return [
        (group.permissions.through, "group_id"),
        (user.user_permissions.through, "user_id"),
    ]


def _absorb(apps, db, duplicate, kept) -> None:
    """duplicate の内容の型を指す履歴と権限を kept へ寄せてから、duplicate を消す.

    kept にも同じ codename の権限があれば、duplicate 側の権限の付与先（グループ・ユーザー）を
    kept 側の権限へ移してから消す（内容の型と codename の組は一意なので、付け替えられない）。
    llm_config の 0014 の同名の関数と同じ（migration はほかの migration に依らないので写す）。
    """
    Permission = apps.get_model("auth", "Permission")
    LogEntry = apps.get_model("admin", "LogEntry")
    permissions = Permission.objects.using(db)
    LogEntry.objects.using(db).filter(content_type=duplicate).update(content_type=kept)
    kept_permissions = {
        permission.codename: permission
        for permission in permissions.filter(content_type=kept)
    }
    holders = _permission_holders(apps)
    for permission in permissions.filter(content_type=duplicate):
        twin = kept_permissions.get(permission.codename)
        if twin is None:
            permissions.filter(pk=permission.pk).update(content_type=kept)
            continue
        for through, owner in holders:
            rows = through.objects.using(db)
            for owner_id in rows.filter(permission=permission).values_list(
                owner, flat=True
            ):
                rows.get_or_create(**{owner: owner_id, "permission": twin})
        permission.delete(using=db)
    duplicate.delete(using=db)


def _rename_default_permissions(apps, db, content_type, from_key, to_key) -> None:
    """内容の型の既定の権限の codename と表示名を、to_key のモデルのものに改める."""
    Permission = apps.get_model("auth", "Permission")
    for action in PERMISSION_ACTIONS:
        Permission.objects.using(db).filter(
            content_type=content_type, codename=f"{action}_{from_key[1]}"
        ).update(
            codename=f"{action}_{to_key[1]}",
            name=f"Can {action} {VERBOSE_NAMES[to_key]}",
        )


def _move_content_type(apps, schema_editor, from_key, to_key) -> None:
    """プロンプトの内容の型の行を from_key から to_key のもの（app_label, model）にする."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    db = schema_editor.connection.alias
    content_types = ContentType.objects.using(db)
    source = content_types.filter(app_label=from_key[0], model=from_key[1]).first()
    if source is None:
        return
    # 移す先の行と codename をそろえてから寄せる（同じ codename の権限を 1 つにする）
    _rename_default_permissions(apps, db, source, from_key, to_key)
    target = content_types.filter(app_label=to_key[0], model=to_key[1]).first()
    if target is not None:
        _absorb(apps, db, duplicate=target, kept=source)
    source.app_label, source.model = to_key
    source.save(using=db, update_fields=["app_label", "model"])
    ContentType.objects.clear_cache()


def move_content_type_to_llm_config(apps, schema_editor):
    """内容の型の行を langfuse_integration から llm_config へ付け替える."""
    _move_content_type(apps, schema_editor, OLD_CONTENT_TYPE, NEW_CONTENT_TYPE)


def move_content_type_to_langfuse_integration(apps, schema_editor):
    """内容の型の行を llm_config から langfuse_integration へ戻す."""
    _move_content_type(apps, schema_editor, NEW_CONTENT_TYPE, OLD_CONTENT_TYPE)


class Migration(migrations.Migration):
    dependencies = [
        ("llm_config", "0017_alter_llmserviceconfig_service_name"),
        ("langfuse_integration", "0003_seed_new_agent_refs"),
        # 内容の型を付け替えるときに、権限とその付与先（グループ・ユーザー）・履歴も扱う
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 何かを変える前に止まれるよう、最初に検査する（戻すときは何もしない）
        migrations.RunPython(
            check_names_can_become_langfuse_prompt_names, migrations.RunPython.noop
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Prompt",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "name",
                            models.CharField(
                                help_text=(
                                    "Django 内で一意に識別する名前"
                                    "（例: hn-agent-orchestrator-system）"
                                ),
                                max_length=100,
                                unique=True,
                                verbose_name="識別名",
                            ),
                        ),
                        (
                            "langfuse_prompt_name",
                            models.CharField(
                                help_text="Langfuse 上で登録されているプロンプト名",
                                max_length=200,
                                verbose_name="Langfuseプロンプト名",
                            ),
                        ),
                        (
                            "label",
                            models.CharField(
                                default="production",
                                help_text=(
                                    "Langfuse のプロンプトラベル（production, staging 等）"
                                ),
                                max_length=50,
                                verbose_name="ラベル",
                            ),
                        ),
                        (
                            "fallback_text",
                            models.TextField(
                                blank=True,
                                default="",
                                help_text=(
                                    "Langfuse 接続失敗・プロンプト未登録時に使用するテキスト"
                                ),
                                verbose_name="フォールバックテキスト",
                            ),
                        ),
                        (
                            "description",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="このプロンプトの用途説明",
                                max_length=255,
                                verbose_name="説明",
                            ),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, verbose_name="作成日時"
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(
                                auto_now=True, verbose_name="更新日時"
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Prompt",
                        "verbose_name_plural": "Prompts",
                        "ordering": ["name"],
                        "db_table": "langfuse_integration_langfusepromptref",
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(
            move_content_type_to_llm_config, move_content_type_to_langfuse_integration
        ),
    ]
