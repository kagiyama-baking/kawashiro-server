"""generate → talk アプリラベル移行マイグレーション

テーブル名、ContentType、django_migrationsのアプリラベルを
generate から talk に一括リネームする。
"""

from django.db import migrations


def rename_app_label(apps, schema_editor):
    """generate → talk にアプリラベルを移行."""
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")

    # RenameModelが新しいContentType(talk, talkconfig)を作成済みの場合、
    # 古いContentType(generate, *)を削除するだけでよい
    ContentType.objects.using(db_alias).filter(app_label="generate").delete()


def revert_app_label(apps, schema_editor):
    """talk → generate にアプリラベルを戻す."""
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")

    ContentType.objects.using(db_alias).filter(
        app_label="talk", model="talkconfig"
    ).update(app_label="generate")
    # モデル名も戻す（RenameModelのrevertで処理されるため不要だが安全のため）


class Migration(migrations.Migration):
    dependencies = [
        ("talk", "0009_rename_app_greeting_to_generate"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # モデルリネーム: GreetingConfig → TalkConfig
        migrations.RenameModel(
            old_name="GreetingConfig",
            new_name="TalkConfig",
        ),
        # テーブルリネーム: generate_greetingconfig → talk_talkconfig
        migrations.AlterModelTable(
            name="talkconfig",
            table="talk_talkconfig",
        ),
        # ContentType 更新
        migrations.RunPython(rename_app_label, revert_app_label),
        # verbose_name 更新
        migrations.AlterModelOptions(
            name="talkconfig",
            options={
                "verbose_name": "会話生成設定",
                "verbose_name_plural": "会話生成設定",
            },
        ),
    ]
