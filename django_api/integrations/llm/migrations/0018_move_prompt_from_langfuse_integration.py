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

戻すときは `migrate llm_config 0017`（設定の付け替えと古いモデルの削除も外れ、プロンプトは
langfuse_integration のモデルに戻る。内容の型の行も同じ規則で戻す）。
"""

from django.conf import settings
from django.db import migrations, models

# 内容の型（ContentType）の (app_label, model) と、既定の権限の表示名に使うモデルの表示名
OLD_CONTENT_TYPE = ("langfuse_integration", "langfusepromptref")
NEW_CONTENT_TYPE = ("llm_config", "prompt")
VERBOSE_NAMES = {OLD_CONTENT_TYPE: "Langfuseプロンプト参照", NEW_CONTENT_TYPE: "Prompt"}
# Django が作る既定の権限の操作（codename は `<操作>_<モデル名>`）
PERMISSION_ACTIONS = ("add", "change", "delete", "view")


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
                            models.DateTimeField(auto_now=True, verbose_name="更新日時"),
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
