"""talk アプリのシグナル."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ChatMessage


@receiver(post_delete, sender=ChatMessage)
def delete_audio_file_on_message_delete(
    sender, instance: ChatMessage, using=None, **kwargs
) -> None:
    """ChatMessage の削除がコミットされたら、音声ファイルをストレージから物理削除する.

    ロールバックで行が戻るのにファイルだけが消えないよう、コミットを待つ。削除自体は
    確定しているので、ファイルの削除に失敗してもログだけ残す（robust）。
    """
    if instance.audio_file:
        storage, name = instance.audio_file.storage, instance.audio_file.name
        transaction.on_commit(lambda: storage.delete(name), using=using, robust=True)
