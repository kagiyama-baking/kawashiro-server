"""greeting → generate アプリラベル移行マイグレーション

テーブル名、ContentType、django_migrationsのアプリラベルを
greeting から generate に一括リネームする。
"""

from django.db import migrations


def rename_app_label(apps, schema_editor):
    """greeting → generate にアプリラベルを移行."""
    db_alias = schema_editor.connection.alias

    # ContentType のアプリラベルを更新
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.using(db_alias).filter(app_label="greeting").update(
        app_label="generate"
    )


def revert_app_label(apps, schema_editor):
    """generate → greeting にアプリラベルを戻す."""
    db_alias = schema_editor.connection.alias

    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.using(db_alias).filter(app_label="generate").update(
        app_label="greeting"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("talk", "0008_change_tts_format_default_to_wav"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # テーブルリネーム
        migrations.AlterModelTable(
            name="greetingconfig",
            table="generate_greetingconfig",
        ),
        # ContentType 更新
        migrations.RunPython(rename_app_label, revert_app_label),
    ]
