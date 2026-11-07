"""旧会話生成（Talk Generator）のプリセットの表と、チャットの旧プリセット名の列を消す.

0018 でチャットを Talk 設定へ移した後に当たる（紐づけた Talk 設定はそのまま残る）。
プリセット（`TalkConfig`）は表ごと消し、旧プリセット名（`ChatSession.config_name`）は
列ごと消す。プリセットが参照していたプロンプト参照（`LangfusePromptRef`）は消さない。

後退では、空のプリセットの表と、空文字の旧プリセット名の列を作り直すだけで、消した
プリセットと旧プリセット名は戻らない。0018 までのコード（イメージだけ戻した旧版）は
この列と表を読むので、旧版に戻すときは先にこの版のコードで 0018 まで戻す。
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("talk", "0018_bind_chat_sessions_to_talk_settings"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="chatsession",
            name="config_name",
        ),
        migrations.DeleteModel(
            name="TalkConfig",
        ),
    ]
