"""ChatSession 内音声ファイルの配信 / 個別削除 / 一括削除 ビュー."""

import mimetypes

from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema
from rest_framework import authentication, permissions, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import ChatMessage
from ._common import get_owned_session

_AUDIO_CONTENT_TYPE = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
}


class ChatSessionMessageAudioView(APIView):
    """個別メッセージの音声配信 / 削除."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    def _get_message(self, request, session_id, msg_id) -> ChatMessage:
        msg = ChatMessage.objects.filter(
            id=msg_id,
            session_id=session_id,
            session__user=request.user,
        ).first()
        if msg is None:
            raise Http404
        return msg

    @extend_schema(tags=["talk"], summary="音声ファイルを配信（認可付き）")
    def get(self, request, session_id, msg_id):
        msg = self._get_message(request, session_id, msg_id)
        if not msg.audio_file:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # ボリューム喪失等で DB 行は残っているが実体が消えているケースを 404 化
        # （素直に open すると FileNotFoundError → 500 になる）
        name = msg.audio_file.name
        if not name or not msg.audio_file.storage.exists(name):
            return Response(status=status.HTTP_404_NOT_FOUND)
        content_type = _AUDIO_CONTENT_TYPE.get(
            msg.audio_format,
            mimetypes.guess_type(name)[0] or "application/octet-stream",
        )
        return FileResponse(msg.audio_file.open("rb"), content_type=content_type)

    @extend_schema(tags=["talk"], summary="個別メッセージの音声だけ削除")
    def delete(self, request, session_id, msg_id):
        msg = self._get_message(request, session_id, msg_id)
        if msg.audio_file:
            msg.audio_file.delete(save=False)
            msg.audio_file = None
        msg.audio_format = ""
        msg.audio_size_bytes = 0
        msg.save(update_fields=["audio_file", "audio_format", "audio_size_bytes"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatSessionAudioBulkDeleteView(APIView):
    """セッション内の音声をすべて削除（メッセージ本文は残す）."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["talk"],
        summary="セッション内の音声を一括削除（テキストは残す）",
    )
    def delete(self, request, session_id):
        session = get_owned_session(request, session_id)
        if session is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        for msg in session.messages.exclude(audio_file=""):
            if msg.audio_file:
                msg.audio_file.delete(save=False)
                msg.audio_file = None
            msg.audio_format = ""
            msg.audio_size_bytes = 0
            msg.save(update_fields=["audio_file", "audio_format", "audio_size_bytes"])
        return Response(status=status.HTTP_204_NO_CONTENT)
