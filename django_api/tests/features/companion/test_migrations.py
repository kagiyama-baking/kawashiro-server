"""companion の migration のテスト（既存の行が移行後にどうなるか）."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from features.companion.models import CompanionConfig
from integrations.langfuse.models import LangfusePromptRef

BEFORE_RENAME = [("companion", "0001_initial")]
AFTER_RENAME = [("companion", "0002_rename_persona_prompt_ref_to_system_prompt_ref")]

CONFIG_NAME = "companion-migration-test"
PROMPT_REF_NAME = "companion-migration-test-system"

# 収集時（テスト DB を作る前）の接続先。pytest-django は、DB を使うと宣言した
# テスト（django_db マーカーなど）が 1 つも収集されないとテスト DB を作らないので、
# このモジュールだけを実行すると、接続先は開発用の DB（.env の DB_ENGINE、
# 未設定なら db.sqlite3）のままになる。
CONFIGURED_DB_NAME = connection.settings_dict["NAME"]


@pytest.fixture
def migrator(django_db_setup, django_db_blocker):
    """migration を行き来し、後始末ですべて当てた状態に戻して、作った行だけ消す.

    スキーマを変えるので、テストのトランザクションの外で動かす（transactional_db を
    使わない理由は tests/features/talk/test_migrations.py の migrator と同じ）。
    DB の遮断を自分で外すので、テスト DB ができていなければ触る前に中止する。
    """
    if connection.settings_dict["NAME"] == CONFIGURED_DB_NAME:
        pytest.fail(
            "テスト DB が作られていないので、開発用の DB の migration を動かさないよう"
            "中止します。tests/features/companion/ のように、DB を使うテストと一緒に"
            "実行してください。"
        )
    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        yield executor
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        # 参照は設定から PROTECT で参照されるので、設定から消す
        CompanionConfig.objects.filter(name=CONFIG_NAME).delete()
        LangfusePromptRef.objects.filter(name=PROMPT_REF_NAME).delete()


def _migrate(migrator, targets):
    """targets まで当て（戻し）、その時点のモデルを引ける apps を返す."""
    migrator.loader.build_graph()
    migrator.migrate(targets)
    return migrator.loader.project_state(targets).apps


def _create_config_before_rename(apps) -> int:
    """0001 の時点のモデルで、参照を persona_prompt_ref に持つ設定を作り、参照の pk を返す."""
    prompt_ref = apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(name=PROMPT_REF_NAME, langfuse_prompt_name=PROMPT_REF_NAME)
    apps.get_model("companion", "CompanionConfig").objects.create(
        name=CONFIG_NAME, persona_prompt_ref=prompt_ref
    )
    return prompt_ref.pk


def _config(apps):
    """その時点のモデルで、テスト用に作った設定を読む."""
    return apps.get_model("companion", "CompanionConfig").objects.get(name=CONFIG_NAME)


@pytest.mark.integration
def test_0002_keeps_prompt_ref_of_existing_config_as_system_prompt_ref(migrator):
    """0001 で作った設定の参照先は、0002 の後も system_prompt_ref として同じまま."""
    prompt_ref_pk = _create_config_before_rename(_migrate(migrator, BEFORE_RENAME))

    new_apps = _migrate(migrator, AFTER_RENAME)

    assert _config(new_apps).system_prompt_ref_id == prompt_ref_pk


@pytest.mark.integration
def test_0002_reverse_restores_prompt_ref_as_persona_prompt_ref(migrator):
    """0001 へ戻すと、参照先は persona_prompt_ref として同じまま戻る."""
    prompt_ref_pk = _create_config_before_rename(_migrate(migrator, BEFORE_RENAME))
    _migrate(migrator, AFTER_RENAME)

    reverted_apps = _migrate(migrator, BEFORE_RENAME)

    assert _config(reverted_apps).persona_prompt_ref_id == prompt_ref_pk
