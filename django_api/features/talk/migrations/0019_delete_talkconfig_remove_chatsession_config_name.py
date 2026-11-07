"""旧会話生成（Talk Generator）のプリセットの表を消し、チャットの旧プリセット名をモデルから外す.

0018 でチャットを Talk 設定へ移した後に当たる（紐づけた Talk 設定はそのまま残る）。
プリセット（`TalkConfig`）は表ごと消す。プリセットが参照していたプロンプト参照
（`LangfusePromptRef`）は消さない。

旧プリセット名（`ChatSession.config_name`）は、モデルからは外すが DB の列は値ごと残す。
イメージだけ #268 の版（0018 まで）に戻しても、旧版のコードがこの列を読み書きして
チャットが動くようにするため。いまのコードは列を書かないので、DB の既定値（空文字）を
付ける。列は後の掃除の migration で消す。

後退では、空のプリセットの表を作り直し、旧プリセット名の列から DB の既定値を外す
（列の値はそのまま）。消したプリセットは戻らない。
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("talk", "0018_bind_chat_sessions_to_talk_settings"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AlterField(
                    model_name="chatsession",
                    name="config_name",
                    field=models.CharField(
                        blank=True,
                        db_default="",
                        default="",
                        help_text=(
                            "Talk 設定より前のチャットのプリセット名（移行の元）。"
                            "新しいチャットでは空"
                        ),
                        max_length=50,
                        verbose_name="旧プリセット名（廃止予定）",
                    ),
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="chatsession",
                    name="config_name",
                ),
            ],
        ),
        migrations.DeleteModel(
            name="TalkConfig",
        ),
    ]
