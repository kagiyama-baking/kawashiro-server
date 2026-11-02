"""ChatSession 内メッセージの送信 / 編集再送 ビュー.

検証だけを行い、実行は `chat_turn` に任せる（`Accept` で SSE / JSON を切り替える）。
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import authentication, permissions, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

# chat_turn の属性を直接 import しない理由は `_sse.py` を参照
from .. import chat_turn
from ..models import ChatMessage
from ..serializers import (
    ChatSessionDetailSerializer,
    SessionMessageEditSerializer,
    SessionMessageInputSerializer,
)
from ._common import get_owned_session
from ._sse import SSE_MEDIA_TYPE, SSE_RESPONSE, respond_with_turn


class ChatSessionMessageView(APIView):
    """セッションへのメッセージ送信（LLM 応答生成）."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "talk_chat"
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["talk"],
        summary="セッションへユーザーメッセージを送信し assistant 応答を生成",
        request=SessionMessageInputSerializer,
        responses={
            201: OpenApiResponse(response=ChatSessionDetailSerializer),
            (200, SSE_MEDIA_TYPE): SSE_RESPONSE,
            400: OpenApiResponse(description="入力不正 / メッセージ件数上限"),
            401: OpenApiResponse(description="認証エラー"),
            404: OpenApiResponse(description="セッションまたは設定が見つからない"),
            406: OpenApiResponse(description="Accept が text/event-stream のみ"),
            502: OpenApiResponse(description="LLM/TTS 等の外部サービスエラー"),
            504: OpenApiResponse(description="外部サービスタイムアウト"),
        },
    )
    def post(self, request, session_id):
        session = get_owned_session(request, session_id)
        if session is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        in_serializer = SessionMessageInputSerializer(data=request.data)
        if not in_serializer.is_valid():
            return Response(in_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = chat_turn.prepare_turn(
                session, in_serializer.validated_data["content"]
            )
        except chat_turn.ChatTurnRejectedError as rejected:
            return Response(rejected.payload, status=rejected.status_code)
        return respond_with_turn(request, plan, status.HTTP_201_CREATED)


class ChatSessionMessageEditView(APIView):
    """既存ユーザーメッセージの編集再送（対象以降を全削除して再生成）."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "talk_chat"
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["talk"],
        summary="メッセージを編集して再送（対象以降は破棄）",
        request=SessionMessageEditSerializer,
        responses={
            (200, SSE_MEDIA_TYPE): SSE_RESPONSE,
            200: OpenApiResponse(response=ChatSessionDetailSerializer),
            400: OpenApiResponse(description="入力不正 / assistant 編集不可"),
            401: OpenApiResponse(description="認証エラー"),
            404: OpenApiResponse(description="セッション/メッセージが見つからない"),
            406: OpenApiResponse(description="Accept が text/event-stream のみ"),
            502: OpenApiResponse(description="LLM/TTS 等の外部サービスエラー"),
            504: OpenApiResponse(description="外部サービスタイムアウト"),
        },
    )
    def patch(self, request, session_id, msg_id):
        session = get_owned_session(request, session_id)
        if session is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # IDOR 二重チェック: msg_id 単独でも所有権を確認する。
        # ChatMessage.id はグローバル連番のため、URL で他人/他 session の
        # msg_id を渡されても 404 にする。
        target = ChatMessage.objects.filter(
            id=msg_id,
            session_id=session.id,
            session__user=request.user,
        ).first()
        if target is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if target.role != "user":
            return Response(
                {"error": "編集できるのは user メッセージのみです"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        in_serializer = SessionMessageEditSerializer(data=request.data)
        if not in_serializer.is_valid():
            return Response(in_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = chat_turn.prepare_turn(
                session,
                in_serializer.validated_data["content"],
                edit_target=target,
            )
        except chat_turn.ChatTurnRejectedError as rejected:
            return Response(rejected.payload, status=rejected.status_code)
        return respond_with_turn(request, plan, status.HTTP_200_OK)
