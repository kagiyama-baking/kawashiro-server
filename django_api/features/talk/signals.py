"""talk アプリのシグナル."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ChatMessage


@receiver(post_delete, sender=ChatMessage)
def delete_audio_file_on_message_delete(
    sender, instance: ChatMessage, **kwargs
) -> None:
    """ChatMessage 削除時、音声ファイルをストレージから物理削除する."""
    if instance.audio_file:
        instance.audio_file.delete(save=False)
