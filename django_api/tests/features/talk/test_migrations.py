"""talk の migration のテスト（既存の行が移行後にどうなるか）."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader

from features.talk.models import TalkConfig
from integrations.langfuse.models import LangfusePromptRef

BEFORE_RATE_LIMIT = [("talk", "0015_chatsession_chatmessage_and_more")]
AFTER_RATE_LIMIT = [("talk", "0016_talkconfig_synthesize_rate_limit")]

LEGACY_CONFIG_NAME = "legacy"
LEGACY_PROMPT_REF_NAME = "talk-legacy"


@pytest.fixture
def migrator(django_db_setup, django_db_blocker):
    """migration を行き来し、後始末ですべて当てた状態に戻して、作った行だけ消す.

    スキーマを変えるので、テストのトランザクションの外で動かす。transactional_db は
    後始末で全テーブルを空にし、data migration で入れた行（HN のプロンプト参照など）
    まで消すので使わない（並び順しだいで、後に流れるテストが落ちる）。
    """
    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        yield executor
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        TalkConfig.objects.filter(name=LEGACY_CONFIG_NAME).delete()
        LangfusePromptRef.objects.filter(name=LEGACY_PROMPT_REF_NAME).delete()


@pytest.mark.integration
def test_0016_sets_rate_limit_10_on_existing_configs(migrator):
    """移行前からあるプリセットの生成回数の上限は 10 になる."""
    migrator.migrate(BEFORE_RATE_LIMIT)
    old_apps = migrator.loader.project_state(BEFORE_RATE_LIMIT).apps
    prompt_ref = old_apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(
        name=LEGACY_PROMPT_REF_NAME,
        langfuse_prompt_name=LEGACY_PROMPT_REF_NAME,
        fallback_text="既存のプロンプト",
    )
    old_apps.get_model("talk", "TalkConfig").objects.create(
        name=LEGACY_CONFIG_NAME,
        display_name="既存のプリセット",
        system_prompt_ref=prompt_ref,
        user_prompt_ref=prompt_ref,
    )

    migrator.loader.build_graph()
    migrator.migrate(AFTER_RATE_LIMIT)

    new_apps = migrator.loader.project_state(AFTER_RATE_LIMIT).apps
    config = new_apps.get_model("talk", "TalkConfig").objects.get(
        name=LEGACY_CONFIG_NAME
    )
    assert config.synthesize_rate_limit == 10


@pytest.mark.integration
@pytest.mark.django_db
def test_0016_lets_code_without_rate_limit_create_configs():
    """0016 の後も、上限の列を知らないコード（イメージだけ戻したとき）がプリセットを作れる.

    0015 時点のモデルは INSERT に上限の列を含めないので、DB の既定値で 10 になる。
    """
    old_apps = MigrationLoader(connection).project_state(BEFORE_RATE_LIMIT).apps
    prompt_ref = old_apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(
        name=LEGACY_PROMPT_REF_NAME,
        langfuse_prompt_name=LEGACY_PROMPT_REF_NAME,
        fallback_text="旧版のプロンプト",
    )

    old_apps.get_model("talk", "TalkConfig").objects.create(
        name=LEGACY_CONFIG_NAME,
        display_name="旧版で作ったプリセット",
        system_prompt_ref=prompt_ref,
        user_prompt_ref=prompt_ref,
    )

    assert TalkConfig.objects.get(name=LEGACY_CONFIG_NAME).synthesize_rate_limit == 10
