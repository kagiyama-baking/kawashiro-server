"""プロンプト（Prompt）を AI設定（llm_config）へ移す migration のテスト.

llm_config の 0018 は、langfuse_integration の LangfusePromptRef を、表を変えずに llm_config の
Prompt にする（状態だけ）。HN Agent の 0018 は 8 本の外部キーの向き先を、Companion の 0008・
Talk の 0020 はシステムプロンプトの向き先を Prompt に替え、項目を system_prompt_ref から
system_prompt に改める（列の名前が変わる）。langfuse_integration の 0004 が古いモデルを状態から
消す。行・外部キーの値・表がそのまま残ることと、戻し方（`migrate llm_config 0017`）で元に戻る
ことを確かめる。0018 は、権限と管理画面の履歴が指す内容の型（ContentType）も付け替える
（移す先の行もあれば 1 つにまとめる）。

0018 は最初に、続く 0019 が名前を Langfuse のプロンプト名にできるかを検査し、できない参照
（Langfuse のプロンプト名が空・前後の空白や改行・重なり）があれば何も変えずに止まる。
名前の付け替え（0019）のテストは test_prompt_rename_migrations.py、共通の時点とヘルパは
tests/fixtures/prompt_migrations.py、フィクスチャ（`prompt_migrator`）は conftest.py。
"""

import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection

from integrations.llm.models import Prompt
from tests.fixtures.migrations import prompt_model
from tests.fixtures.prompt_migrations import (
    AFTER_MOVE,
    AFTER_RENAME,
    ALL_MIGRATIONS,
    BEFORE_MOVE,
    HN_PROMPT_FIELDS,
    LLM_BEFORE_MOVE,
    ROLLBACK,
    SYSTEM_PROMPT_NAME,
    TEMPORARY_PREFIX,
    TEST_GROUP_NAME,
    TEST_PREFIX,
    TEST_USER_EMAIL,
    applied_migrations,
    chosen_prompts,
    column_names,
    create_configs,
    create_prompt,
    migrate_to,
    prompt_rows,
)

# 既定の権限の操作と、移す前後の内容の型（app_label, model）・権限の表示に使うモデルの表示名
PERMISSION_ACTIONS = ("add", "change", "delete", "view")
OLD_CONTENT_TYPE = ("langfuse_integration", "langfusepromptref")
NEW_CONTENT_TYPE = ("llm_config", "prompt")
OLD_VERBOSE_NAME = "Langfuseプロンプト参照"
NEW_VERBOSE_NAME = "Prompt"


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
def test_move_keeps_prompt_rows_in_llm_config_model(prompt_migrator):
    """移した後は、移す前と同じ行（pk と全部の項目）を llm_config の Prompt で読める."""
    apps = migrate_to(prompt_migrator, BEFORE_MOVE)
    create_prompt(
        apps,
        SYSTEM_PROMPT_NAME,
        langfuse_prompt_name="prompt-move-test-langfuse",
        label="staging",
        fallback_text="本文",
        description="説明",
    )
    rows = prompt_rows(apps, [SYSTEM_PROMPT_NAME])

    new_apps = migrate_to(prompt_migrator, AFTER_MOVE)

    assert prompt_model(new_apps)._meta.label == "llm_config.Prompt"
    assert prompt_rows(new_apps, [SYSTEM_PROMPT_NAME]) == rows


@pytest.mark.integration
def test_move_keeps_table_and_creates_no_llm_config_table(prompt_migrator):
    """表は langfuse_integration の 0001 が作った表のまま。llm_config の表は作らない."""
    migrate_to(prompt_migrator, BEFORE_MOVE)

    migrate_to(prompt_migrator, AFTER_MOVE)

    tables = connection.introspection.table_names()
    assert "langfuse_integration_langfusepromptref" in tables
    assert "llm_config_prompt" not in tables


@pytest.mark.integration
def test_move_keeps_prompts_chosen_by_configs(prompt_migrator):
    """HN Agent 設定の 8 本と、Companion 設定・Talk 設定のシステムプロンプトは同じプロンプトを指す."""
    chosen = create_configs(migrate_to(prompt_migrator, BEFORE_MOVE))

    new_apps = migrate_to(prompt_migrator, AFTER_MOVE)

    assert chosen_prompts(new_apps) == chosen
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
def test_move_renames_system_prompt_column(prompt_migrator, table):
    """Companion 設定・Talk 設定のシステムプロンプトの列は system_prompt_id になる."""
    migrate_to(prompt_migrator, BEFORE_MOVE)
    assert "system_prompt_ref_id" in column_names(table)

    migrate_to(prompt_migrator, AFTER_MOVE)

    columns = column_names(table)
    assert "system_prompt_id" in columns
    assert "system_prompt_ref_id" not in columns


@pytest.mark.integration
def test_rollback_to_llm_config_0017_unapplies_all_six_migrations(prompt_migrator):
    """戻し方（`migrate llm_config 0017`）で、移す 5 本と名前を付け替える 0019 がすべて外れる."""
    assert ALL_MIGRATIONS.issubset(applied_migrations())

    migrate_to(prompt_migrator, ROLLBACK)

    assert ALL_MIGRATIONS.isdisjoint(applied_migrations())
    assert LLM_BEFORE_MOVE in applied_migrations()


@pytest.mark.integration
def test_rollback_restores_old_columns_and_keeps_chosen_prompts(prompt_migrator):
    """戻すと列が system_prompt_ref_id に戻り、設定は同じプロンプトを LangfusePromptRef で指す."""
    chosen = create_configs(migrate_to(prompt_migrator, BEFORE_MOVE))
    migrate_to(prompt_migrator, AFTER_MOVE)

    migrate_to(prompt_migrator, ROLLBACK)

    old_apps = prompt_migrator.loader.project_state(BEFORE_MOVE).apps
    assert (
        prompt_model(old_apps)._meta.label == "langfuse_integration.LangfusePromptRef"
    )
    assert chosen_prompts(old_apps) == chosen
    for table in ("companion_companionconfig", "talk_talksetting"):
        columns = column_names(table)
        assert "system_prompt_ref_id" in columns
        assert "system_prompt_id" not in columns


@pytest.mark.integration
def test_move_moves_content_type_with_its_id_and_renames_permissions(prompt_migrator):
    """移すと、内容の型の行が同じ id のまま llm_config の prompt になり、既定の権限も改まる."""
    migrate_to(prompt_migrator, BEFORE_MOVE)
    original = _content_type(OLD_CONTENT_TYPE)
    permission_ids = set(
        Permission.objects.filter(content_type=original).values_list("pk", flat=True)
    )

    migrate_to(prompt_migrator, AFTER_MOVE)

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
def test_rollback_moves_content_type_back_with_old_permissions(prompt_migrator):
    """戻すと、内容の型の行（同じ id）が langfuse_integration に戻り、権限も元の名前に戻る."""
    moved = _content_type(NEW_CONTENT_TYPE)

    migrate_to(prompt_migrator, ROLLBACK)

    assert _prompt_content_types() == [(*OLD_CONTENT_TYPE, moved.pk)]
    assert _permissions(moved) == _default_permissions(
        "langfusepromptref", OLD_VERBOSE_NAME
    )


@pytest.mark.integration
def test_move_keeps_admin_history_visible_for_prompt_model(prompt_migrator):
    """移す前の管理画面の履歴が、移した後のモデル（llm_config の Prompt）の履歴に出る."""
    prompt = create_prompt(migrate_to(prompt_migrator, BEFORE_MOVE), SYSTEM_PROMPT_NAME)
    entry = _log_change(_test_user(), _content_type(OLD_CONTENT_TYPE), prompt.pk)

    migrate_to(prompt_migrator, AFTER_MOVE)

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
def test_move_keeps_permission_given_before_move(prompt_migrator):
    """移す前に付けた権限（change_langfusepromptref）は、llm_config の change_prompt として残る."""
    migrate_to(prompt_migrator, BEFORE_MOVE)
    user = _test_user()
    user.user_permissions.add(
        Permission.objects.get(
            content_type=_content_type(OLD_CONTENT_TYPE),
            codename="change_langfusepromptref",
        )
    )

    migrate_to(prompt_migrator, AFTER_MOVE)

    assert list(
        Permission.objects.filter(user=user).values_list(
            "content_type__app_label", "codename"
        )
    ) == [("llm_config", "change_prompt")]


@pytest.mark.integration
def test_move_with_both_content_types_keeps_one_row_and_one_set_of_permissions(
    prompt_migrator,
):
    """移す先の行もあっても（戻した後の migrate が作った行など）、一意の制約に触れずに 1 つにまとめる.

    残すのは移す前の行（id はそのまま）で、既定の権限は 1 組だけになる。
    """
    migrate_to(prompt_migrator, BEFORE_MOVE)
    original = _content_type(OLD_CONTENT_TYPE)
    _create_duplicate_content_type(NEW_CONTENT_TYPE, NEW_VERBOSE_NAME)

    migrate_to(prompt_migrator, AFTER_MOVE)

    assert _prompt_content_types() == [(*NEW_CONTENT_TYPE, original.pk)]
    assert _permissions(original) == _default_permissions("prompt", NEW_VERBOSE_NAME)


@pytest.mark.integration
def test_move_with_both_content_types_moves_history_and_permissions_to_kept_row(
    prompt_migrator,
):
    """まとめるときは、消す行の履歴と、その行の権限の付与（ユーザー・グループ）を残す行へ移す."""
    prompt = create_prompt(migrate_to(prompt_migrator, BEFORE_MOVE), SYSTEM_PROMPT_NAME)
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

    migrate_to(prompt_migrator, AFTER_MOVE)

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
    prompt_migrator,
):
    """戻すときも、戻す先の行があれば 1 つにまとめる（残すのは移した行。権限は元の名前）."""
    moved = _content_type(NEW_CONTENT_TYPE)
    _create_duplicate_content_type(OLD_CONTENT_TYPE, OLD_VERBOSE_NAME)

    migrate_to(prompt_migrator, ROLLBACK)

    assert _prompt_content_types() == [(*OLD_CONTENT_TYPE, moved.pk)]
    assert _permissions(moved) == _default_permissions(
        "langfusepromptref", OLD_VERBOSE_NAME
    )


@pytest.mark.integration
def test_move_with_duplicate_langfuse_prompt_names_stops_before_changing_anything(
    prompt_migrator,
):
    """Langfuse のプロンプト名が重なる参照があれば、0018 の最初で止まり、何も変えない.

    名前は Langfuse のプロンプト名になり一意なので、重なると付け替えられない。エラーには、
    重なる参照（識別名・Langfuse のプロンプト名@ラベル）を挙げる（重ならない参照は挙げない）。
    """
    apps = migrate_to(prompt_migrator, BEFORE_MOVE)
    shared = f"{TEST_PREFIX}shared"
    create_prompt(apps, f"{TEST_PREFIX}a", langfuse_prompt_name=shared)
    create_prompt(apps, f"{TEST_PREFIX}b", langfuse_prompt_name=shared, label="staging")
    create_prompt(apps, f"{TEST_PREFIX}other")
    original = _content_type(OLD_CONTENT_TYPE)
    rows = prompt_rows(apps, [f"{TEST_PREFIX}a", f"{TEST_PREFIX}b"])

    with pytest.raises(RuntimeError) as exc_info:
        migrate_to(prompt_migrator, AFTER_RENAME)

    message = str(exc_info.value)
    assert "何も変えていません" in message
    assert f"{TEST_PREFIX}a（{shared}@production）" in message
    assert f"{TEST_PREFIX}b（{shared}@staging）" in message
    assert f"{TEST_PREFIX}other" not in message
    assert ALL_MIGRATIONS.isdisjoint(applied_migrations())
    stopped_apps = prompt_migrator.loader.project_state(BEFORE_MOVE).apps
    assert prompt_rows(stopped_apps, [f"{TEST_PREFIX}a", f"{TEST_PREFIX}b"]) == rows
    assert _prompt_content_types() == [(*OLD_CONTENT_TYPE, original.pk)]


@pytest.mark.integration
@pytest.mark.parametrize(
    "langfuse_prompt_name",
    [
        pytest.param("", id="empty"),
        pytest.param("  ", id="spaces_only"),
        pytest.param(" prompt-move-test-x", id="leading_space"),
        pytest.param("prompt-move-test-x\n", id="trailing_newline"),
        pytest.param("prompt-move-test\nx", id="newline_inside"),
        pytest.param(TEST_PREFIX + "x" * 184, id="201_chars"),
    ],
)
def test_move_with_unusable_langfuse_prompt_name_stops_and_names_the_ref(
    prompt_migrator, langfuse_prompt_name
):
    """Langfuse のプロンプト名が名前にできない（空・前後の空白や改行・途中の改行・200 字超）なら止める."""
    apps = migrate_to(prompt_migrator, BEFORE_MOVE)
    create_prompt(apps, f"{TEST_PREFIX}bad", langfuse_prompt_name=langfuse_prompt_name)

    with pytest.raises(RuntimeError) as exc_info:
        migrate_to(prompt_migrator, AFTER_RENAME)

    assert f"{TEST_PREFIX}bad" in str(exc_info.value)
    assert ALL_MIGRATIONS.isdisjoint(applied_migrations())


@pytest.mark.integration
def test_move_with_name_starting_with_temporary_prefix_stops(prompt_migrator):
    """名前が 0019 の一時の名前（__llm_config_0019__/）で始まる参照があれば止める."""
    apps = migrate_to(prompt_migrator, BEFORE_MOVE)
    create_prompt(apps, f"{TEMPORARY_PREFIX}1")

    with pytest.raises(RuntimeError, match=TEMPORARY_PREFIX):
        migrate_to(prompt_migrator, AFTER_RENAME)

    assert ALL_MIGRATIONS.isdisjoint(applied_migrations())
