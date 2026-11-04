"""llm_config の migration のテスト（既存の行が移行後にどうなるか）."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from integrations.llm.models import LLMProviderConfig, LLMServiceConfig

BEFORE_COMPANION = [("llm_config", "0012_add_new_agent_service_choices")]
AFTER_COMPANION = [("llm_config", "0013_add_companion_service_choice")]

PROVIDER_NAME = "llm-migration-test"
OTHER_PROVIDER_NAME = "llm-migration-test-other"

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
            "中止します。tests/integrations/llm/ のように、DB を使うテストと一緒に"
            "実行してください。"
        )
    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        yield executor
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        # LLM 設定は PROTECT で参照されるので、サービス設定から消す
        names = (PROVIDER_NAME, OTHER_PROVIDER_NAME)
        LLMServiceConfig.objects.filter(provider_config__name__in=names).delete()
        LLMProviderConfig.objects.filter(name__in=names).delete()


def _migrate(migrator, targets):
    """targets まで当て（戻し）、その時点のモデルを引ける apps を返す."""
    migrator.loader.build_graph()
    migrator.migrate(targets)
    return migrator.loader.project_state(targets).apps


def _create_service(apps, service_name, *, provider_name, **fields):
    """provider_name の LLM 設定を作り、それを使う service_name のサービス設定を作る."""
    provider = apps.get_model("llm_config", "LLMProviderConfig").objects.create(
        name=provider_name, model_alias=f"{provider_name}-alias"
    )
    return apps.get_model("llm_config", "LLMServiceConfig").objects.create(
        service_name=service_name, provider_config=provider, **fields
    )


def _services(apps):
    """その時点の LLMServiceConfig のマネージャを返す."""
    return apps.get_model("llm_config", "LLMServiceConfig").objects


@pytest.mark.integration
def test_0013_with_talk_clones_it_as_inactive_companion(migrator):
    """talk の行があれば、同じ LLM 設定とタイムアウトで無効の companion を作る."""
    old_apps = _migrate(migrator, BEFORE_COMPANION)
    talk = _create_service(
        old_apps, "talk", provider_name=PROVIDER_NAME, is_active=True, timeout=123
    )

    new_apps = _migrate(migrator, AFTER_COMPANION)

    companion = _services(new_apps).get(service_name="companion")
    assert companion.provider_config_id == talk.provider_config_id
    assert companion.timeout == 123
    assert companion.is_active is False


@pytest.mark.integration
def test_0013_without_talk_creates_no_companion(migrator):
    """talk の行がなければ、ほかのサービスの行があっても companion は作らない."""
    old_apps = _migrate(migrator, BEFORE_COMPANION)
    _create_service(old_apps, "detective", provider_name=PROVIDER_NAME)

    new_apps = _migrate(migrator, AFTER_COMPANION)

    assert not _services(new_apps).filter(service_name="companion").exists()


@pytest.mark.integration
def test_0013_with_existing_companion_keeps_it_unchanged(migrator):
    """companion の行がすでにあれば、talk の内容で作り直さず、そのまま残す."""
    old_apps = _migrate(migrator, BEFORE_COMPANION)
    _create_service(old_apps, "talk", provider_name=PROVIDER_NAME, timeout=30)
    existing = _create_service(
        old_apps,
        "companion",
        provider_name=OTHER_PROVIDER_NAME,
        is_active=True,
        timeout=90,
    )

    new_apps = _migrate(migrator, AFTER_COMPANION)

    companion = _services(new_apps).get(service_name="companion")
    assert companion.pk == existing.pk
    assert companion.provider_config_id == existing.provider_config_id
    assert companion.timeout == 90
    assert companion.is_active is True


@pytest.mark.integration
def test_0013_reverse_removes_companion_and_keeps_talk(migrator):
    """0012 へ戻すと companion の行は消え、雛形の talk の行は残る."""
    old_apps = _migrate(migrator, BEFORE_COMPANION)
    _create_service(old_apps, "talk", provider_name=PROVIDER_NAME)
    _migrate(migrator, AFTER_COMPANION)

    reverted_apps = _migrate(migrator, BEFORE_COMPANION)

    assert not _services(reverted_apps).filter(service_name="companion").exists()
    assert _services(reverted_apps).filter(service_name="talk").exists()
