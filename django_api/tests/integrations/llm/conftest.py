"""integrations/llm のテストの共通フィクスチャ."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from tests.fixtures.migrations import applied_apps
from tests.fixtures.prompt_migrations import delete_test_rows

# 収集時（テスト DB を作る前）の接続先。pytest-django は、DB を使うと宣言した
# テスト（django_db マーカーなど）が 1 つも収集されないとテスト DB を作らないので、
# migration のテストだけを実行すると、接続先は開発用の DB（.env の DB_ENGINE、
# 未設定なら db.sqlite3）のままになる。
CONFIGURED_DB_NAME = connection.settings_dict["NAME"]


@pytest.fixture
def prompt_migrator(django_db_setup, django_db_blocker):
    """プロンプトの migration を行き来し、後始末で作った行を消してから、すべて当てた状態に戻す.

    test_prompt_move_migrations.py と test_prompt_rename_migrations.py が使う。
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
        delete_test_rows(applied_apps(executor))
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        ContentType.objects.clear_cache()
