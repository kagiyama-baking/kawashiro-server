"""Agent Skills を companion から llm_config へ移す migration のテスト.

llm_config の 0014 と companion の 0006 は、DB を変えずにモデルの持ち主だけを替える
（状態だけの migration）。行・設定の選択・表がそのまま残ることと、戻し方
（`migrate llm_config 0013`）で companion のモデルに戻ることを確かめる。
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

CONFIG_NAME = "agent-skill-move-test"
PROMPT_REF_NAME = "agent-skill-move-test-system"
MORNING = "move-test-morning"
NIGHT = "move-test-night"
TEST_SKILL_NAMES = (MORNING, NIGHT)

# 収集時（テスト DB を作る前）の接続先。pytest-django は、DB を使うと宣言した
# テスト（django_db マーカーなど）が 1 つも収集されないとテスト DB を作らないので、
# このモジュールだけを実行すると、接続先は開発用の DB（.env の DB_ENGINE、
# 未設定なら db.sqlite3）のままになる。
CONFIGURED_DB_NAME = connection.settings_dict["NAME"]


@pytest.fixture
def migrator(django_db_setup, django_db_blocker):
    """migration を行き来し、後始末ですべて当てた状態に戻して、作った行だけ消す.

    migration を当て外しするので、テストのトランザクションの外で動かす（transactional_db
    を使わない理由は tests/features/talk/test_migrations.py の migrator と同じ）。
    DB の遮断を自分で外すので、テスト DB ができていなければ触る前に中止する。
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
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        CompanionConfig.objects.filter(name=CONFIG_NAME).delete()
        AgentSkill.objects.filter(name__in=TEST_SKILL_NAMES).delete()
        LangfusePromptRef.objects.filter(name=PROMPT_REF_NAME).delete()


def _migrate(migrator, targets):
    """targets まで当て（戻し）、その時点のモデルを引ける apps を返す."""
    migrator.loader.build_graph()
    migrator.migrate(targets)
    return migrator.loader.project_state(targets).apps


def _create_config_selecting_skills(apps) -> list:
    """移す前の時点のモデルで、スキル 2 つを選んだ設定を作り、スキルを名前順に返す."""
    prompt_ref = apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(name=PROMPT_REF_NAME, langfuse_prompt_name=PROMPT_REF_NAME)
    skills = apps.get_model("companion", "AgentSkill").objects
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


def _skill_rows(skills) -> list[tuple]:
    """スキルの行の中身（pk・名前・説明・ラベル・有効）."""
    return [
        (skill.pk, skill.name, skill.description, skill.label, skill.is_enabled)
        for skill in skills
    ]


def _test_skills(apps, app_label: str) -> list:
    """その時点のモデル（app_label の AgentSkill）で、テスト用のスキルを名前順に読む."""
    return list(
        apps.get_model(app_label, "AgentSkill")
        .objects.filter(name__in=TEST_SKILL_NAMES)
        .order_by("name")
    )


def _selected_skill_names(apps) -> list[str]:
    """その時点のモデルで、テスト用の設定が選んでいるスキルの名前（名前順）."""
    config = apps.get_model("companion", "CompanionConfig").objects.get(
        name=CONFIG_NAME
    )
    return [skill.name for skill in config.skills.order_by("name")]


@pytest.mark.integration
def test_0006_moved_skills_keep_rows_in_llm_config_model(migrator):
    """移した後は、移す前と同じ行（pk・名前・説明・ラベル・有効）を llm_config のモデルで読める."""
    skills = _create_config_selecting_skills(_migrate(migrator, BEFORE_MOVE))

    new_apps = _migrate(migrator, AFTER_MOVE)

    assert _skill_rows(_test_skills(new_apps, "llm_config")) == _skill_rows(skills)


@pytest.mark.integration
def test_0006_moved_skills_stay_selected_in_config(migrator):
    """移した後も、設定はそれまでと同じスキルを選んでいる."""
    _create_config_selecting_skills(_migrate(migrator, BEFORE_MOVE))

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
def test_0014_reverse_also_unapplies_companion_0006(migrator):
    """llm_config 0013 へ戻すと、0014 に続く companion 0006 も外れる（companion 0005 は残る）."""
    _migrate(migrator, AFTER_MOVE)

    _migrate(migrator, [LLM_BEFORE_MOVE])

    applied = MigrationRecorder(connection).applied_migrations()
    assert LLM_MOVE not in applied
    assert COMPANION_MOVE not in applied
    assert COMPANION_BEFORE_MOVE in applied


@pytest.mark.integration
def test_0014_reverse_returns_skills_and_selection_to_companion_model(migrator):
    """llm_config 0013 へ戻すと、同じ行と設定の選択を companion のモデルで読める."""
    skills = _create_config_selecting_skills(_migrate(migrator, BEFORE_MOVE))
    _migrate(migrator, AFTER_MOVE)

    _migrate(migrator, [LLM_BEFORE_MOVE])

    reverted_apps = migrator.loader.project_state(BEFORE_MOVE).apps
    assert _skill_rows(_test_skills(reverted_apps, "companion")) == _skill_rows(skills)
    assert _selected_skill_names(reverted_apps) == [MORNING, NIGHT]
