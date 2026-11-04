"""Agent Skills の migration のテスト（companion からの移動と、名前の付け替え）.

llm_config の 0014 と companion の 0006 は、DB を変えずにモデルの持ち主だけを替える
（状態だけの migration）。行・設定の選択・表がそのまま残ることと、戻し方
（`migrate llm_config 0013`）で companion のモデルに戻ることを確かめる。

llm_config の 0015 は、スキル名を本文の Langfuse のプロンプト名そのものにする。本文を読む
先を変えないよう、前進ではいまある全部の行の名前に接頭辞 companion-skill- を付け、後退では
接頭辞の付いた行だけから外す。止まるとき（64 字を超える・名前が重なる）は何も変えない。
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from features.companion.models import CompanionConfig
from integrations.langfuse.models import LangfusePromptRef
from integrations.llm.models import AgentSkill

# 移す前の時点（AgentSkill は companion のモデル）
LLM_BEFORE_MOVE = ("llm_config", "0013_add_companion_service_choice")
COMPANION_BEFORE_MOVE = ("companion", "0005_delete_companionskill")
BEFORE_MOVE = [LLM_BEFORE_MOVE, COMPANION_BEFORE_MOVE]
# 移す migration（companion の 0006 は llm_config の 0014 の後に当たる）
LLM_MOVE = ("llm_config", "0014_move_agentskill_from_companion")
COMPANION_MOVE = ("companion", "0006_move_agentskill_to_llm_config")
AFTER_MOVE = [COMPANION_MOVE]
# 名前を付け替える前（移した後）の時点と、付け替える migration
BEFORE_RENAME = [LLM_MOVE, COMPANION_MOVE]
RENAME = ("llm_config", "0015_agentskill_name_is_prompt_name")
AFTER_RENAME = [RENAME]

# 0015 より前の、本文のプロンプト名の接頭辞（0015 の前進でスキル名に付ける）
PREFIX = "companion-skill-"

CONFIG_NAME = "agent-skill-move-test"
PROMPT_REF_NAME = "agent-skill-move-test-system"
MORNING = "move-test-morning"
NIGHT = "move-test-night"
# 接頭辞を付けると、ちょうど 64 字（名前の上限）になる名前と、65 字になる名前
LONGEST = "move-test-" + "a" * 38
TOO_LONG = "move-test-" + "b" * 39
TEST_SKILL_NAMES = (MORNING, NIGHT, LONGEST, TOO_LONG)
# 後始末で消す名前（接頭辞なし・1 つ付き・2 つ付きのどれで残っていても消す）
CLEANUP_SKILL_NAMES = tuple(
    f"{PREFIX * count}{name}" for name in TEST_SKILL_NAMES for count in range(3)
)

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
    作った行は当て直す前に消す（0015 は名前を付け替え、64 字を超える名前があると止まる
    ため）。このモジュールが行き来する時点では表が同じなので、いまのモデルで消せる。
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
        CompanionConfig.objects.filter(name=CONFIG_NAME).delete()
        AgentSkill.objects.filter(name__in=CLEANUP_SKILL_NAMES).delete()
        LangfusePromptRef.objects.filter(name=PROMPT_REF_NAME).delete()
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())


def _migrate(migrator, targets):
    """targets まで当て（戻し）、その時点のモデルを引ける apps を返す."""
    migrator.loader.build_graph()
    migrator.migrate(targets)
    return migrator.loader.project_state(targets).apps


def _applied_migrations() -> set:
    """DB に当たっている migration."""
    return set(MigrationRecorder(connection).applied_migrations())


def _create_config_selecting_skills(apps, app_label: str) -> list:
    """その時点のモデル（app_label の AgentSkill）で、スキル 2 つを選んだ設定を作る.

    Returns:
        作ったスキル（名前順）
    """
    prompt_ref = apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(name=PROMPT_REF_NAME, langfuse_prompt_name=PROMPT_REF_NAME)
    skills = apps.get_model(app_label, "AgentSkill").objects
    selected = [
        skills.create(name=MORNING, description="朝のあいさつ", label="staging"),
        skills.create(
            name=NIGHT, description="夜のあいさつ", label="production", is_enabled=False
        ),
    ]
    config = apps.get_model("companion", "CompanionConfig").objects.create(
        name=CONFIG_NAME, system_prompt_ref=prompt_ref
    )
    config.skills.add(*selected)
    return selected


def _create_skills(apps, *names: str) -> None:
    """名前を付け替える前後の時点のモデル（llm_config の AgentSkill）で、スキルを順に作る."""
    skills = apps.get_model("llm_config", "AgentSkill").objects
    for name in names:
        skills.create(name=name, description=f"{name} のときに使う", label="staging")


def _skill_rows(skills) -> list[tuple]:
    """スキルの行の中身（pk・名前・説明・ラベル・有効）."""
    return [
        (skill.pk, skill.name, skill.description, skill.label, skill.is_enabled)
        for skill in skills
    ]


def _test_skills(apps, app_label: str = "llm_config") -> list:
    """その時点のモデル（app_label の AgentSkill）で、テスト用のスキルを名前順に読む."""
    return list(
        apps.get_model(app_label, "AgentSkill")
        .objects.filter(name__in=CLEANUP_SKILL_NAMES)
        .order_by("name")
    )


def _test_skill_names(apps, app_label: str = "llm_config") -> list[str]:
    """その時点のモデルで、テスト用のスキルの名前を名前順に読む."""
    return [skill.name for skill in _test_skills(apps, app_label)]


def _selected_skill_names(apps) -> list[str]:
    """その時点のモデルで、テスト用の設定が選んでいるスキルの名前（名前順）."""
    config = apps.get_model("companion", "CompanionConfig").objects.get(
        name=CONFIG_NAME
    )
    return [skill.name for skill in config.skills.order_by("name")]


@pytest.mark.integration
def test_0006_moved_skills_keep_rows_in_llm_config_model(migrator):
    """移した後は、移す前と同じ行（pk・名前・説明・ラベル・有効）を llm_config のモデルで読める."""
    skills = _create_config_selecting_skills(
        _migrate(migrator, BEFORE_MOVE), "companion"
    )

    new_apps = _migrate(migrator, AFTER_MOVE)

    assert _skill_rows(_test_skills(new_apps)) == _skill_rows(skills)


@pytest.mark.integration
def test_0006_moved_skills_stay_selected_in_config(migrator):
    """移した後も、設定はそれまでと同じスキルを選んでいる."""
    _create_config_selecting_skills(_migrate(migrator, BEFORE_MOVE), "companion")

    new_apps = _migrate(migrator, AFTER_MOVE)

    assert _selected_skill_names(new_apps) == [MORNING, NIGHT]


@pytest.mark.integration
def test_0006_keeps_tables_of_skills_and_selection(migrator):
    """表は移す前のまま（companion_agentskill と選択の中間表）。llm_config の表は作らない."""
    _migrate(migrator, BEFORE_MOVE)

    _migrate(migrator, AFTER_MOVE)

    tables = connection.introspection.table_names()
    assert "companion_agentskill" in tables
    assert "companion_companionconfig_skills" in tables
    assert "llm_config_agentskill" not in tables


@pytest.mark.integration
def test_0014_reverse_also_unapplies_0015_and_companion_0006(migrator):
    """llm_config 0013 へ戻すと、0014 に続く 0015 と companion 0006 も外れる（companion 0005 は残る）."""
    _migrate(migrator, AFTER_RENAME)

    _migrate(migrator, [LLM_BEFORE_MOVE])

    applied = _applied_migrations()
    assert {RENAME, COMPANION_MOVE, LLM_MOVE}.isdisjoint(applied)
    assert COMPANION_BEFORE_MOVE in applied


@pytest.mark.integration
def test_0014_reverse_returns_skills_and_selection_to_companion_model(migrator):
    """llm_config 0013 へ戻すと、同じ行と設定の選択を companion のモデルで読める."""
    skills = _create_config_selecting_skills(
        _migrate(migrator, BEFORE_MOVE), "companion"
    )
    _migrate(migrator, AFTER_MOVE)

    _migrate(migrator, [LLM_BEFORE_MOVE])

    reverted_apps = migrator.loader.project_state(BEFORE_MOVE).apps
    assert _skill_rows(_test_skills(reverted_apps, "companion")) == _skill_rows(skills)
    assert _selected_skill_names(reverted_apps) == [MORNING, NIGHT]


@pytest.mark.integration
def test_0015_prefixes_skill_names_keeping_other_fields(migrator):
    """名前に接頭辞が付き（いまの本文のプロンプト名になる）、pk・説明・ラベル・有効はそのまま."""
    skills = _create_config_selecting_skills(
        _migrate(migrator, BEFORE_RENAME), "llm_config"
    )

    new_apps = _migrate(migrator, AFTER_RENAME)

    assert _skill_rows(_test_skills(new_apps)) == [
        (pk, f"{PREFIX}{name}", description, label, is_enabled)
        for pk, name, description, label, is_enabled in _skill_rows(skills)
    ]


@pytest.mark.integration
def test_0015_keeps_selection_of_renamed_skills(migrator):
    """名前を付け替えても、設定はそれまでと同じスキルを選んでいる."""
    _create_config_selecting_skills(_migrate(migrator, BEFORE_RENAME), "llm_config")

    new_apps = _migrate(migrator, AFTER_RENAME)

    assert _selected_skill_names(new_apps) == [PREFIX + MORNING, PREFIX + NIGHT]


@pytest.mark.integration
def test_0015_with_name_equal_to_prefixed_other_name_renames_both(migrator):
    """ほかのスキルに接頭辞を付けた名前のスキルがあっても、重ならずに両方へ付ける.

    名前の長い順に付け替える。短い方を先に作るので、作った順に付け替えると一意の制約で止まる。
    """
    _create_skills(_migrate(migrator, BEFORE_RENAME), MORNING, PREFIX + MORNING)

    new_apps = _migrate(migrator, AFTER_RENAME)

    assert _test_skill_names(new_apps) == [PREFIX + PREFIX + MORNING, PREFIX + MORNING]


@pytest.mark.integration
def test_0015_with_48_char_name_prefixes_it_to_64_chars(migrator):
    """接頭辞を付けてちょうど 64 字（名前の上限）になる名前は付け替える."""
    _create_skills(_migrate(migrator, BEFORE_RENAME), LONGEST)

    new_apps = _migrate(migrator, AFTER_RENAME)

    assert _test_skill_names(new_apps) == [PREFIX + LONGEST]
    assert len(PREFIX + LONGEST) == 64


@pytest.mark.integration
def test_0015_with_name_over_64_chars_after_prefix_stops_and_renames_nothing(
    migrator,
):
    """接頭辞を付けると 64 字を超える名前があれば止め、ほかのスキルの名前も変えない.

    起動時の migrate が止まる（0015 は当たらない）。エラーには、直すべきスキルの名前を挙げる。
    """
    _create_skills(_migrate(migrator, BEFORE_RENAME), MORNING, TOO_LONG)

    with pytest.raises(RuntimeError) as exc_info:
        _migrate(migrator, AFTER_RENAME)

    message = str(exc_info.value)
    assert TOO_LONG in message
    assert MORNING not in message
    assert RENAME not in _applied_migrations()
    stopped_apps = migrator.loader.project_state(BEFORE_RENAME).apps
    assert _test_skill_names(stopped_apps) == sorted([MORNING, TOO_LONG])


@pytest.mark.integration
def test_0015_reverse_strips_prefix_and_leaves_unprefixed_skill(migrator):
    """戻すと、接頭辞の付いた名前からだけ外し、0015 の後に接頭辞なしで登録したスキルは変えない."""
    _create_skills(_migrate(migrator, BEFORE_RENAME), MORNING)
    _create_skills(_migrate(migrator, AFTER_RENAME), NIGHT)

    reverted_apps = _migrate(migrator, BEFORE_RENAME)

    assert _test_skill_names(reverted_apps) == [MORNING, NIGHT]


@pytest.mark.integration
def test_0015_reverse_with_doubly_prefixed_name_strips_one_prefix_from_each(
    migrator,
):
    """接頭辞が 2 つ付いた名前と 1 つ付いた名前があっても、重ならずに 1 つずつ外す.

    名前の短い順に外す。2 つ付いた方を先に作るので、作った順に外すと一意の制約で止まる。
    """
    _create_skills(
        _migrate(migrator, AFTER_RENAME), PREFIX + PREFIX + MORNING, PREFIX + MORNING
    )

    reverted_apps = _migrate(migrator, BEFORE_RENAME)

    assert _test_skill_names(reverted_apps) == [PREFIX + MORNING, MORNING]


@pytest.mark.integration
def test_0015_reverse_with_stripped_name_taken_stops_and_keeps_0015_applied(migrator):
    """外した名前のスキルがすでにあれば止め、どの名前も変えない（0015 は当たったまま）.

    エラーには、重なる名前を挙げる（重ならないスキルは挙げない）。
    """
    _create_skills(
        _migrate(migrator, AFTER_RENAME), PREFIX + MORNING, MORNING, PREFIX + NIGHT
    )

    with pytest.raises(RuntimeError) as exc_info:
        _migrate(migrator, BEFORE_RENAME)

    message = str(exc_info.value)
    assert PREFIX + MORNING in message
    assert NIGHT not in message
    assert RENAME in _applied_migrations()
    stopped_apps = migrator.loader.project_state(AFTER_RENAME).apps
    assert _test_skill_names(stopped_apps) == sorted(
        [PREFIX + MORNING, MORNING, PREFIX + NIGHT]
    )


@pytest.mark.integration
def test_rollback_to_llm_config_0013_restores_original_names_in_companion_model(
    migrator,
):
    """戻し方（`migrate llm_config 0013`）では、名前が接頭辞のない元の名前に戻り、companion のモデルで読める."""
    _create_config_selecting_skills(_migrate(migrator, BEFORE_MOVE), "companion")
    _migrate(migrator, AFTER_RENAME)

    _migrate(migrator, [LLM_BEFORE_MOVE])

    reverted_apps = migrator.loader.project_state(BEFORE_MOVE).apps
    assert _test_skill_names(reverted_apps, "companion") == [MORNING, NIGHT]
    assert _selected_skill_names(reverted_apps) == [MORNING, NIGHT]
