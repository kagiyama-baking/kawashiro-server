"""talk の migration のテスト（既存の行が移行後にどうなるか）."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE_RATE_LIMIT = [("talk", "0015_chatsession_chatmessage_and_more")]
AFTER_RATE_LIMIT = [("talk", "0016_talkconfig_synthesize_rate_limit")]


@pytest.fixture
def migrator(transactional_db):
    """migration を行き来し、テストの後はすべて当てた状態に戻す.

    スキーマを変えるので transactional_db を使う（テストの後に DB は空になる）。
    """
    executor = MigrationExecutor(connection)
    yield executor
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.integration
def test_0016_sets_rate_limit_10_on_existing_configs(migrator):
    """移行前からあるプリセットの生成回数の上限は 10 になる."""
    migrator.migrate(BEFORE_RATE_LIMIT)
    old_apps = migrator.loader.project_state(BEFORE_RATE_LIMIT).apps
    prompt_ref = old_apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(
        name="talk-legacy",
        langfuse_prompt_name="talk-legacy",
        fallback_text="既存のプロンプト",
    )
    old_apps.get_model("talk", "TalkConfig").objects.create(
        name="legacy",
        display_name="既存のプリセット",
        system_prompt_ref=prompt_ref,
        user_prompt_ref=prompt_ref,
    )

    migrator.loader.build_graph()
    migrator.migrate(AFTER_RATE_LIMIT)

    new_apps = migrator.loader.project_state(AFTER_RATE_LIMIT).apps
    config = new_apps.get_model("talk", "TalkConfig").objects.get(name="legacy")
    assert config.synthesize_rate_limit == 10
