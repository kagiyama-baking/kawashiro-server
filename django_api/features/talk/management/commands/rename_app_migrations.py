"""django_migrationsテーブルのアプリラベルをリネームするコマンド.

Djangoアプリのリネーム時に、既存のマイグレーション記録を新しいアプリ名に
更新するために使用する。migrate実行前に実行すること。
"""

from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError, connection


class Command(BaseCommand):
    """django_migrationsテーブルのapp列をリネーム."""

    help = "django_migrationsテーブルのアプリラベルをリネームする"

    def add_arguments(self, parser):
        """コマンド引数を定義."""
        parser.add_argument("old_app", type=str, help="旧アプリラベル")
        parser.add_argument("new_app", type=str, help="新アプリラベル")

    def handle(self, *args, **options):
        """コマンドを実行."""
        old_app = options["old_app"]
        new_app = options["new_app"]

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE django_migrations SET app=%s WHERE app=%s",
                    [new_app, old_app],
                )
                count = cursor.rowcount
        except (OperationalError, ProgrammingError):
            # django_migrationsテーブルが未作成の場合（初回migrate前）
            self.stdout.write(
                self.style.NOTICE(
                    "django_migrationsテーブルが未作成のためスキップ"
                )
            )
            return

        if count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"django_migrations: {old_app} → {new_app} ({count}件更新)"
                )
            )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    f"django_migrations: {old_app} のレコードなし（更新不要）"
                )
            )
