# Migration to remove MSGraphConfig from onedrive (moved to ms_graph)

from django.db import migrations


class Migration(migrations.Migration):
    """
    onedrive.MSGraphConfigモデルを削除するマイグレーション

    実際のテーブルはms_graphアプリに移動済みのため、
    Djangoの状態からモデル定義を削除するだけです。
    """

    dependencies = [
        ("onedrive", "0002_multiple_configs"),
        ("ms_graph", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name="MSGraphConfig",
                ),
            ],
            # テーブルは既にms_graphにリネーム済みなので、DB操作は不要
            database_operations=[],
        ),
    ]
