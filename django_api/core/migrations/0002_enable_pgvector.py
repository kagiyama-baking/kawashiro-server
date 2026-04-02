"""pgvector extensionを有効化するマイグレーション."""

from django.db import connection, migrations


def enable_pgvector(apps, schema_editor):
    """PostgreSQLの場合のみpgvector extensionを有効化."""
    if connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def disable_pgvector(apps, schema_editor):
    """PostgreSQLの場合のみpgvector extensionを無効化."""
    if connection.vendor == "postgresql":
        schema_editor.execute("DROP EXTENSION IF EXISTS vector;")


class Migration(migrations.Migration):
    """PostgreSQLにpgvector extensionを追加."""

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_pgvector, disable_pgvector),
    ]
