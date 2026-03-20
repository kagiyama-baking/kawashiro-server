# Migration to move MSGraphConfig from onedrive to msgraph_config

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    onedrive.MSGraphConfigをmsgraph_config.MSGraphConfigに移行するマイグレーション

    既存のonedrive_msgraphconfigテーブルをmsgraph_config_msgraphconfigにリネームします。
    """

    initial = True

    dependencies = [
        ("onedrive", "0002_multiple_configs"),
    ]

    operations = [
        # テーブル名を変更（状態とDBを分離して処理）
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="MSGraphConfig",
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
                                default="デフォルト設定",
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
                            "tenant_id",
                            models.CharField(
                                help_text="Azure AD（Microsoft Entra ID）のテナントID",
                                max_length=255,
                                verbose_name="テナントID",
                            ),
                        ),
                        (
                            "client_id",
                            models.CharField(
                                help_text="Azure ADアプリケーションのクライアントID",
                                max_length=255,
                                verbose_name="クライアントID",
                            ),
                        ),
                        (
                            "cert_thumbprint",
                            models.CharField(
                                help_text="証明書のサムプリント（拇印）",
                                max_length=255,
                                verbose_name="証明書サムプリント",
                            ),
                        ),
                        (
                            "target_user",
                            models.CharField(
                                help_text="Microsoft Graph APIでアクセスする対象ユーザーのメールアドレスまたはユーザーID",
                                max_length=255,
                                verbose_name="対象ユーザー",
                            ),
                        ),
                        (
                            "_encrypted_private_key",
                            models.TextField(
                                blank=True,
                                db_column="encrypted_private_key",
                                default="",
                                verbose_name="暗号化された秘密鍵",
                            ),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, verbose_name="作成日時"
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(auto_now=True, verbose_name="更新日時"),
                        ),
                    ],
                    options={
                        "verbose_name": "Microsoft Graph API設定",
                        "verbose_name_plural": "Microsoft Graph API設定",
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "onedrive_msgraphconfig" RENAME TO "msgraph_config_msgraphconfig"',
                    reverse_sql='ALTER TABLE "msgraph_config_msgraphconfig" RENAME TO "onedrive_msgraphconfig"',
                ),
            ],
        ),
    ]
