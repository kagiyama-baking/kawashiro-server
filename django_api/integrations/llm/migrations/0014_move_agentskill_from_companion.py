"""Agent Skills（AgentSkill）を companion から llm_config へ移す（表は変えない）.

表は companion の 0003 が作った companion_agentskill をそのまま使う（db_table）。この後の
companion の 0006 が、設定の選択（CompanionConfig.skills）の向き先をこのモデルに替え、
companion 側のモデルを状態から消す。どちらも表を変えないので、行・選択・表は残る。

権限と管理画面の履歴は内容の型（ContentType）の行を指すので、その行のアプリ名も companion
から llm_config へ付け替える（id はそのままなので、付けた権限も履歴も移したモデルで見える）。
companion の行がなければ何もしない（新しい DB では、内容の型は migrate の後に作られる）。
llm_config の行もあれば（戻した後の migrate が作った行など）、その行を指す履歴と権限を
companion の行へ寄せてから消し、companion の行を付け替える（行は 1 つにまとまる）。

戻すときは `migrate llm_config 0013`（companion の 0006 も外れ、AgentSkill は companion の
モデルに戻る。内容の型の行も同じ規則で companion に戻す）。
"""

import django.core.validators
from django.conf import settings
from django.db import migrations, models

import integrations.llm.models

# 内容の型（ContentType）の model（AgentSkill のモデル名）
SKILL_MODEL_NAME = "agentskill"


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


def _move_content_type(apps, schema_editor, from_app_label, to_app_label) -> None:
    """AgentSkill の内容の型の行を from_app_label から to_app_label のものにする."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    db = schema_editor.connection.alias
    content_types = ContentType.objects.using(db)
    source = content_types.filter(
        app_label=from_app_label, model=SKILL_MODEL_NAME
    ).first()
    if source is None:
        return
    target = content_types.filter(
        app_label=to_app_label, model=SKILL_MODEL_NAME
    ).first()
    if target is not None:
        _absorb(apps, db, duplicate=target, kept=source)
    source.app_label = to_app_label
    source.save(using=db, update_fields=["app_label"])
    ContentType.objects.clear_cache()


def move_content_type_to_llm_config(apps, schema_editor):
    """内容の型の行を companion から llm_config へ付け替える."""
    _move_content_type(apps, schema_editor, "companion", "llm_config")


def move_content_type_to_companion(apps, schema_editor):
    """内容の型の行を llm_config から companion へ戻す."""
    _move_content_type(apps, schema_editor, "llm_config", "companion")


class Migration(migrations.Migration):
    dependencies = [
        ("llm_config", "0013_add_companion_service_choice"),
        ("companion", "0005_delete_companionskill"),
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
                    name="AgentSkill",
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
                                    "英小文字・数字・ハイフン（例: good-morning）、64 字以内。"
                                    "先頭・末尾・連続のハイフンは使えない。本文は、名前の前に "
                                    "companion-skill- を付けた Langfuse の text プロンプト"
                                    "（例: companion-skill-good-morning）から読むので、"
                                    "名前を変えると本文を読む先も変わる"
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
                        (
                            "description",
                            models.CharField(
                                help_text=(
                                    "どんな発話のときに使うスキルか（例: 朝のあいさつ。"
                                    "「おはよう」など）。モデルはこの説明を読んで使うスキルを選ぶ。"
                                    "1024 字以内"
                                ),
                                max_length=1024,
                                verbose_name="説明",
                            ),
                        ),
                        (
                            "label",
                            models.CharField(
                                default="production",
                                help_text=(
                                    "本文を取る Langfuse のプロンプトのラベル"
                                    "（staging / production）"
                                ),
                                max_length=50,
                                verbose_name="ラベル",
                            ),
                        ),
                        (
                            "is_enabled",
                            models.BooleanField(
                                default=True,
                                help_text="無効にしたスキルは、設定で選んでいても使わない",
                                verbose_name="有効",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Agent Skill",
                        "verbose_name_plural": "Agent Skills",
                        "ordering": ["name"],
                        "db_table": "companion_agentskill",
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(
            move_content_type_to_llm_config, move_content_type_to_companion
        ),
    ]
