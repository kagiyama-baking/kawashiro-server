# Generated manually for llm_config app

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    LLM設定アプリの初期マイグレーション

    既存のassistant_openaiconfigテーブルがある場合はリネーム、
    なければ新規作成を行う。
    """

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="OpenAIConfig",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="この設定を識別するための名前（例：本番環境、テスト環境）",
                        max_length=255,
                        unique=True,
                        verbose_name="設定名",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=False,
                        help_text="この設定を有効にする（有効にできるのは1つの設定のみ）",
                        verbose_name="有効",
                    ),
                ),
                (
                    "timeout",
                    models.IntegerField(
                        default=60,
                        help_text="APIリクエストのタイムアウト秒数",
                        verbose_name="タイムアウト（秒）",
                    ),
                ),
                (
                    "_encrypted_api_key",
                    models.TextField(
                        blank=True,
                        db_column="encrypted_api_key",
                        default="",
                        verbose_name="暗号化されたAPIキー",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="作成日時"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="更新日時"),
                ),
                (
                    "model",
                    models.CharField(
                        default="gpt-4o-mini",
                        help_text="使用するOpenAIモデル（例：gpt-4o-mini, gpt-4o, gpt-5.2-chat-latest）",
                        max_length=255,
                        verbose_name="モデル",
                    ),
                ),
            ],
            options={
                "verbose_name": "OpenAI API設定",
                "verbose_name_plural": "OpenAI API設定",
            },
        ),
    ]
