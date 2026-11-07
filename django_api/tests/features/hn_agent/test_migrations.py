"""HN Agent の migration の依存のテスト."""

import pytest
from django.db.migrations.loader import MigrationLoader

# pgvector の拡張を入れる migration と、vector の列（埋め込み）を作る migration
ENABLE_PGVECTOR = ("core", "0002_enable_pgvector")
VECTOR_COLUMNS = ("hn_agent", "0002_add_embedding_and_investigation")


@pytest.mark.unit
def test_embedding_migration_depends_on_pgvector_extension():
    """vector の列を作る hn_agent 0002 は、pgvector の拡張を入れる core 0002 の後に当たる.

    依存がないと、新しい PostgreSQL の DB で、ほかのアプリの migration の依存から HN Agent の
    migration が core より先に当たったとき（llm_config 0018 は hn_agent 0017 に依存する）、
    `type "vector" does not exist` で止まる。
    """
    graph = MigrationLoader(None, ignore_no_migrations=True).graph

    assert ENABLE_PGVECTOR in graph.forwards_plan(VECTOR_COLUMNS)
