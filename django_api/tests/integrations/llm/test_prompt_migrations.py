"""プロンプト（Prompt）を AI設定（llm_config）へ移す migration のテスト.

llm_config の 0018 は、langfuse_integration の LangfusePromptRef を、表を変えずに llm_config の
Prompt にする（状態だけ）。HN Agent の 0018 は 8 本の外部キーの向き先を、Companion の 0008・
Talk の 0020 はシステムプロンプトの向き先を Prompt に替え、項目を system_prompt_ref から
system_prompt に改める（列の名前が変わる）。langfuse_integration の 0004 が古いモデルを状態から
消す。行・外部キーの値・表がそのまま残ることと、戻し方（`migrate llm_config 0017`）で元に戻る
ことを確かめる。0018 は、権限と管理画面の履歴が指す内容の型（ContentType）も付け替える
（移す先の行もあれば 1 つにまとめる）。
"""

import pytest
from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from integrations.llm.models import Prompt
from tests.fixtures.migrations import applied_apps, prompt_model, system_prompt_field

# 移す前の時点（プロンプトは langfuse_integration の LangfusePromptRef）。戻し方は llm_config 0017
LLM_BEFORE_MOVE = ("llm_config", "0017_alter_llmserviceconfig_service_name")
BEFORE_MOVE = [
    LLM_BEFORE_MOVE,
    ("hn_agent", "0017_make_new_agent_prompt_refs_required"),
    ("companion", "0007_alter_companionconfig_skills_related_name"),
    ("talk", "0019_delete_talkconfig_remove_chatsession_config_name"),
    ("langfuse_integration", "0003_seed_new_agent_refs"),
]
ROLLBACK = [LLM_BEFORE_MOVE]
# 移す migration（langfuse_integration の 0004 は、HN Agent・Companion・Talk の付け替えの後）
MOVE = ("llm_config", "0018_move_prompt_from_langfuse_integration")
HN_RETARGET = ("hn_agent", "0018_prompt_fks_to_llm_config")
COMPANION_RENAME = ("companion", "0008_rename_system_prompt_ref_to_system_prompt")
TALK_RENAME = ("talk", "0020_rename_system_prompt_ref_to_system_prompt")
DELETE_OLD = ("langfuse_integration", "0004_delete_langfusepromptref")
AFTER_MOVE = [DELETE_OLD]
MOVE_MIGRATIONS = {MOVE, HN_RETARGET, COMPANION_RENAME, TALK_RENAME, DELETE_OLD}

# HN Agent 設定がプロンプトを選ぶ 8 本の外部キー
HN_PROMPT_FIELDS = (
    "orchestrator_system_prompt",
    "orchestrator_user_prompt",
    "detective_system_prompt",
    "detective_user_prompt",
    "devils_advocate_system_prompt",
    "devils_advocate_user_prompt",
    "security_responder_system_prompt",
    "security_responder_user_prompt",
)

# テストで作る設定とプロンプト（後始末で消す）
CONFIG_NAME = "prompt-move-test"
SYSTEM_PROMPT_NAME = "prompt-move-test-system"
HN_PROMPT_NAMES = tuple(f"prompt-move-test-hn-{field}" for field in HN_PROMPT_FIELDS)
CLEANUP_PROMPT_NAMES = (SYSTEM_PROMPT_NAME, *HN_PROMPT_NAMES)

# 権限と管理画面の履歴を付ける、テスト用のユーザーとグループ
TEST_USER_EMAIL = "prompt-move-test@example.com"
TEST_GROUP_NAME = "prompt-move-test"
# 既定の権限の操作と、移す前後の内容の型（app_label, model）・権限の表示に使うモデルの表示名
PERMISSION_ACTIONS = ("add", "change", "delete", "view")
OLD_CONTENT_TYPE = ("langfuse_integration", "langfusepromptref")
NEW_CONTENT_TYPE = ("llm_config", "prompt")
OLD_VERBOSE_NAME = "Langfuseプロンプト参照"
NEW_VERBOSE_NAME = "Prompt"

# 収集時（テスト DB を作る前）の接続先。pytest-django は、DB を使うと宣言した
# テスト（django_db マーカーなど）が 1 つも収集されないとテスト DB を作らないので、
# このモジュールだけを実行すると、接続先は開発用の DB（.env の DB_ENGINE、
# 未設定なら db.sqlite3）のままになる。
CONFIGURED_DB_NAME = connection.settings_dict["NAME"]


@pytest.fixture
def migrator(django_db_setup, django_db_blocker):
    """migration を行き来し、後始末で作った行を消してから、すべて当てた状態に戻す.

    migration を当て外しするので、テストのトランザクションの外で動かす（transactional_db
    を使わない理由は tests/features/talk/test_migrations.py の migrator と同じ）。
    DB の遮断を自分で外すので、テスト DB ができていなければ触る前に中止する。
    作った行は、いま当たっている時点のモデルで、当て直す前に消す。内容の型（ContentType）の
    行は migration が付け替えるので、当て直した後にキャッシュを空にする（ほかのテストが
    古い行を引かないように）。
    """
    if connection.settings_dict["NAME"] == CONFIGURED_DB_NAME:
        pytest.fail(
            "テスト DB が作られていないので、開発用の DB の migration を動かさないよう"
            "中止します。tests/integrations/llm/ のように、DB を使うテストと一緒に"
            "実行してください。"
        )
    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        yield executor
        _delete_test_rows(applied_apps(executor))
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        ContentType.objects.clear_cache()


def _delete_test_rows(apps) -> None:
    """テストで作った行を消す（プロンプトは設定から PROTECT で参照されるので、設定を先に）."""
    apps.get_model("hn_agent", "HNAgentConfig").objects.filter(
        name=CONFIG_NAME
    ).delete()
    apps.get_model("companion", "CompanionConfig").objects.filter(
        name=CONFIG_NAME
    ).delete()
    apps.get_model("talk", "TalkSetting").objects.filter(name=CONFIG_NAME).delete()
    prompt_model(apps).objects.filter(name__in=CLEANUP_PROMPT_NAMES).delete()
    # ユーザーを消すと、そのユーザーの履歴と権限の付与も消える
    apps.get_model(settings.AUTH_USER_MODEL).objects.filter(
        email=TEST_USER_EMAIL
    ).delete()
    apps.get_model("auth", "Group").objects.filter(name=TEST_GROUP_NAME).delete()


def _migrate(migrator, targets):
    """targets まで当て（戻し）、その時点のモデルを引ける apps を返す."""
    migrator.loader.build_graph()
    migrator.migrate(targets)
    return migrator.loader.project_state(targets).apps


def _applied_migrations() -> set:
    """DB に当たっている migration."""
    return set(MigrationRecorder(connection).applied_migrations())


def _create_prompt(apps, name: str, **fields):
    """その時点のモデルでプロンプトを作る（Langfuse のプロンプト名は、指定しなければ名前と同じ）."""
    return prompt_model(apps).objects.create(
        name=name, **{"langfuse_prompt_name": name, **fields}
    )


def _create_configs(apps) -> dict[str, int]:
    """その時点のモデルで、プロンプトを選んだ HN Agent 設定・Companion 設定・Talk 設定を作る.

    Returns:
        項目（HN Agent の 8 本と、Companion・Talk のシステムプロンプト）→ 選んだプロンプトの pk
    """
    hn_prompts = {
        field: _create_prompt(apps, name)
        for field, name in zip(HN_PROMPT_FIELDS, HN_PROMPT_NAMES, strict=True)
    }
    apps.get_model("hn_agent", "HNAgentConfig").objects.create(
        name=CONFIG_NAME, **hn_prompts
    )
    system_prompt = _create_prompt(apps, SYSTEM_PROMPT_NAME)
    for app_label, model_name in (
        ("companion", "CompanionConfig"),
        ("talk", "TalkSetting"),
    ):
        model = apps.get_model(app_label, model_name)
        model.objects.create(
            name=CONFIG_NAME, **{system_prompt_field(model): system_prompt}
        )
    return {
        **{field: prompt.pk for field, prompt in hn_prompts.items()},
        "companion": system_prompt.pk,
        "talk": system_prompt.pk,
    }


def _chosen_prompts(apps) -> dict[str, int]:
    """その時点のモデルで、テスト用の設定が選んでいるプロンプトの pk（`_create_configs` と同じ形）."""
    hn_config = apps.get_model("hn_agent", "HNAgentConfig").objects.get(
        name=CONFIG_NAME
    )
    chosen = {field: getattr(hn_config, f"{field}_id") for field in HN_PROMPT_FIELDS}
    for key, (app_label, model_name) in {
        "companion": ("companion", "CompanionConfig"),
        "talk": ("talk", "TalkSetting"),
    }.items():
        model = apps.get_model(app_label, model_name)
        config = model.objects.get(name=CONFIG_NAME)
        chosen[key] = getattr(config, f"{system_prompt_field(model)}_id")
    return chosen


def _prompt_rows(apps, names) -> list[tuple]:
    """その時点のモデルで、プロンプトの行の中身（pk・名前・Langfuse 名・ラベル・本文・説明）を名前順に読む."""
    return list(
        prompt_model(apps)
        .objects.filter(name__in=names)
        .order_by("name")
        .values_list(
            "pk",
            "name",
            "langfuse_prompt_name",
            "label",
            "fallback_text",
            "description",
        )
    )


def _column_names(table: str) -> set[str]:
    """表の列の名前."""
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return {column.name for column in description}


def _prompt_content_types() -> list[tuple[str, str, int]]:
    """プロンプトの内容の型の行（アプリ名・モデル名・id。アプリ名順）."""
    return list(
        ContentType.objects.filter(
            model__in=[OLD_CONTENT_TYPE[1], NEW_CONTENT_TYPE[1]],
            app_label__in=[OLD_CONTENT_TYPE[0], NEW_CONTENT_TYPE[0]],
        )
        .order_by("app_label")
        .values_list("app_label", "model", "pk")
    )


def _content_type(key: tuple[str, str]) -> ContentType:
    """(app_label, model) の内容の型の行."""
    app_label, model = key
    return ContentType.objects.get(app_label=app_label, model=model)


def _permissions(content_type: ContentType) -> list[tuple[str, str]]:
    """内容の型の権限（codename・表示名。codename 順）."""
    return list(
        Permission.objects.filter(content_type=content_type)
        .order_by("codename")
        .values_list("codename", "name")
    )


def _default_permissions(model: str, verbose_name: str) -> list[tuple[str, str]]:
    """Django が作る既定の権限（codename・表示名。codename 順）."""
    return sorted(
        (f"{action}_{model}", f"Can {action} {verbose_name}")
        for action in PERMISSION_ACTIONS
    )


def _create_duplicate_content_type(key: tuple[str, str], verbose_name: str):
    """戻した後の migrate が作る、移す先の内容の型の行と既定の権限を作る."""
    app_label, model = key
    duplicate = ContentType.objects.create(app_label=app_label, model=model)
    for codename, name in _default_permissions(model, verbose_name):
        Permission.objects.create(content_type=duplicate, codename=codename, name=name)
    return duplicate


def _test_user():
    """権限と管理画面の履歴を付ける、テスト用のユーザー."""
    return get_user_model().objects.create_user(
        email=TEST_USER_EMAIL, password="move-test-password"
    )


def _log_change(user, content_type: ContentType, object_id: int) -> LogEntry:
    """管理画面の変更の履歴を 1 件残す."""
    return LogEntry.objects.create(
        user=user,
        content_type=content_type,
        object_id=str(object_id),
        object_repr=f"prompt {object_id}",
        action_flag=CHANGE,
        change_message="変更",
    )


@pytest.mark.integration
def test_move_keeps_prompt_rows_in_llm_config_model(migrator):
    """移した後は、移す前と同じ行（pk と全部の項目）を llm_config の Prompt で読める."""
    apps = _migrate(migrator, BEFORE_MOVE)
    _create_prompt(
        apps,
        SYSTEM_PROMPT_NAME,
        langfuse_prompt_name="prompt-move-test-langfuse",
        label="staging",
        fallback_text="本文",
        description="説明",
    )
    rows = _prompt_rows(apps, [SYSTEM_PROMPT_NAME])

    new_apps = _migrate(migrator, AFTER_MOVE)

    assert prompt_model(new_apps)._meta.label == "llm_config.Prompt"
    assert _prompt_rows(new_apps, [SYSTEM_PROMPT_NAME]) == rows


@pytest.mark.integration
def test_move_keeps_table_and_creates_no_llm_config_table(migrator):
    """表は langfuse_integration の 0001 が作った表のまま。llm_config の表は作らない."""
    _migrate(migrator, BEFORE_MOVE)

    _migrate(migrator, AFTER_MOVE)

    tables = connection.introspection.table_names()
    assert "langfuse_integration_langfusepromptref" in tables
    assert "llm_config_prompt" not in tables


@pytest.mark.integration
def test_move_keeps_prompts_chosen_by_configs(migrator):
    """HN Agent 設定の 8 本と、Companion 設定・Talk 設定のシステムプロンプトは同じプロンプトを指す."""
    chosen = _create_configs(_migrate(migrator, BEFORE_MOVE))

    new_apps = _migrate(migrator, AFTER_MOVE)

    assert _chosen_prompts(new_apps) == chosen
    hn_config = new_apps.get_model("hn_agent", "HNAgentConfig")
    for field in HN_PROMPT_FIELDS:
        related = hn_config._meta.get_field(field).related_model
        assert related._meta.label == "llm_config.Prompt"


@pytest.mark.integration
@pytest.mark.parametrize(
    "table",
    ["companion_companionconfig", "talk_talksetting"],
    ids=["companion", "talk"],
)
def test_move_renames_system_prompt_column(migrator, table):
    """Companion 設定・Talk 設定のシステムプロンプトの列は system_prompt_id になる."""
    _migrate(migrator, BEFORE_MOVE)
    assert "system_prompt_ref_id" in _column_names(table)

    _migrate(migrator, AFTER_MOVE)

    columns = _column_names(table)
    assert "system_prompt_id" in columns
    assert "system_prompt_ref_id" not in columns


@pytest.mark.integration
def test_rollback_to_llm_config_0017_unapplies_all_move_migrations(migrator):
    """戻し方（`migrate llm_config 0017`）で、移す migration がすべて外れる."""
    _migrate(migrator, AFTER_MOVE)

    _migrate(migrator, ROLLBACK)

    assert MOVE_MIGRATIONS.isdisjoint(_applied_migrations())
    assert LLM_BEFORE_MOVE in _applied_migrations()


@pytest.mark.integration
def test_rollback_restores_old_columns_and_keeps_chosen_prompts(migrator):
    """戻すと列が system_prompt_ref_id に戻り、設定は同じプロンプトを LangfusePromptRef で指す."""
    chosen = _create_configs(_migrate(migrator, BEFORE_MOVE))
    _migrate(migrator, AFTER_MOVE)

    _migrate(migrator, ROLLBACK)

    old_apps = migrator.loader.project_state(BEFORE_MOVE).apps
    assert (
        prompt_model(old_apps)._meta.label == "langfuse_integration.LangfusePromptRef"
    )
    assert _chosen_prompts(old_apps) == chosen
    for table in ("companion_companionconfig", "talk_talksetting"):
        columns = _column_names(table)
        assert "system_prompt_ref_id" in columns
        assert "system_prompt_id" not in columns


@pytest.mark.integration
def test_move_moves_content_type_with_its_id_and_renames_permissions(migrator):
    """移すと、内容の型の行が同じ id のまま llm_config の prompt になり、既定の権限も改まる."""
    _migrate(migrator, BEFORE_MOVE)
    original = _content_type(OLD_CONTENT_TYPE)
    permission_ids = set(
        Permission.objects.filter(content_type=original).values_list("pk", flat=True)
    )

    _migrate(migrator, AFTER_MOVE)

    assert _prompt_content_types() == [(*NEW_CONTENT_TYPE, original.pk)]
    assert _permissions(original) == _default_permissions("prompt", NEW_VERBOSE_NAME)
    assert (
        set(
            Permission.objects.filter(content_type=original).values_list(
                "pk", flat=True
            )
        )
        == permission_ids
    )


@pytest.mark.integration
def test_rollback_moves_content_type_back_with_old_permissions(migrator):
    """戻すと、内容の型の行（同じ id）が langfuse_integration に戻り、権限も元の名前に戻る."""
    moved = _content_type(NEW_CONTENT_TYPE)

    _migrate(migrator, ROLLBACK)

    assert _prompt_content_types() == [(*OLD_CONTENT_TYPE, moved.pk)]
    assert _permissions(moved) == _default_permissions(
        "langfusepromptref", OLD_VERBOSE_NAME
    )


@pytest.mark.integration
def test_move_keeps_admin_history_visible_for_prompt_model(migrator):
    """移す前の管理画面の履歴が、移した後のモデル（llm_config の Prompt）の履歴に出る."""
    prompt = _create_prompt(_migrate(migrator, BEFORE_MOVE), SYSTEM_PROMPT_NAME)
    entry = _log_change(_test_user(), _content_type(OLD_CONTENT_TYPE), prompt.pk)

    _migrate(migrator, AFTER_MOVE)

    # 管理画面の履歴と同じく、モデルの内容の型と pk で引く
    ContentType.objects.clear_cache()
    history = LogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(
            Prompt, for_concrete_model=False
        ),
        object_id=str(prompt.pk),
    )
    assert list(history) == [entry]


@pytest.mark.integration
def test_move_keeps_permission_given_before_move(migrator):
    """移す前に付けた権限（change_langfusepromptref）は、llm_config の change_prompt として残る."""
    _migrate(migrator, BEFORE_MOVE)
    user = _test_user()
    user.user_permissions.add(
        Permission.objects.get(
            content_type=_content_type(OLD_CONTENT_TYPE),
            codename="change_langfusepromptref",
        )
    )

    _migrate(migrator, AFTER_MOVE)

    assert list(
        Permission.objects.filter(user=user).values_list(
            "content_type__app_label", "codename"
        )
    ) == [("llm_config", "change_prompt")]


@pytest.mark.integration
def test_move_with_both_content_types_keeps_one_row_and_one_set_of_permissions(
    migrator,
):
    """移す先の行もあっても（戻した後の migrate が作った行など）、一意の制約に触れずに 1 つにまとめる.

    残すのは移す前の行（id はそのまま）で、既定の権限は 1 組だけになる。
    """
    _migrate(migrator, BEFORE_MOVE)
    original = _content_type(OLD_CONTENT_TYPE)
    _create_duplicate_content_type(NEW_CONTENT_TYPE, NEW_VERBOSE_NAME)

    _migrate(migrator, AFTER_MOVE)

    assert _prompt_content_types() == [(*NEW_CONTENT_TYPE, original.pk)]
    assert _permissions(original) == _default_permissions("prompt", NEW_VERBOSE_NAME)


@pytest.mark.integration
def test_move_with_both_content_types_moves_history_and_permissions_to_kept_row(
    migrator,
):
    """まとめるときは、消す行の履歴と、その行の権限の付与（ユーザー・グループ）を残す行へ移す."""
    prompt = _create_prompt(_migrate(migrator, BEFORE_MOVE), SYSTEM_PROMPT_NAME)
    original = _content_type(OLD_CONTENT_TYPE)
    duplicate = _create_duplicate_content_type(NEW_CONTENT_TYPE, NEW_VERBOSE_NAME)
    user = _test_user()
    user.user_permissions.add(
        Permission.objects.get(
            content_type=original, codename="change_langfusepromptref"
        ),
        Permission.objects.get(content_type=duplicate, codename="view_prompt"),
    )
    group = Group.objects.create(name=TEST_GROUP_NAME)
    group.permissions.add(
        Permission.objects.get(content_type=duplicate, codename="add_prompt")
    )
    entries = [_log_change(user, row, prompt.pk) for row in (original, duplicate)]

    _migrate(migrator, AFTER_MOVE)

    assert set(
        LogEntry.objects.filter(user=user).values_list("pk", "content_type_id")
    ) == {(entry.pk, original.pk) for entry in entries}
    assert set(
        Permission.objects.filter(user=user).values_list("content_type_id", "codename")
    ) == {(original.pk, "change_prompt"), (original.pk, "view_prompt")}
    assert list(
        Permission.objects.filter(group=group).values_list(
            "content_type_id", "codename"
        )
    ) == [(original.pk, "add_prompt")]


@pytest.mark.integration
def test_rollback_with_both_content_types_keeps_one_row_with_old_permissions(
    migrator,
):
    """戻すときも、戻す先の行があれば 1 つにまとめる（残すのは移した行。権限は元の名前）."""
    moved = _content_type(NEW_CONTENT_TYPE)
    _create_duplicate_content_type(OLD_CONTENT_TYPE, OLD_VERBOSE_NAME)

    _migrate(migrator, ROLLBACK)

    assert _prompt_content_types() == [(*OLD_CONTENT_TYPE, moved.pk)]
    assert _permissions(moved) == _default_permissions(
        "langfusepromptref", OLD_VERBOSE_NAME
    )
