"""ChatSession 内メッセージの送信 / 編集再送 ビュー."""

import logging

from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import authentication, permissions, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from ..models import ChatMessage, ChatSession, TalkConfig
from ..serializers import (
    ChatSessionDetailSerializer,
    SessionMessageEditSerializer,
    SessionMessageInputSerializer,
)
from ..services import TalkService
from ._common import (
    SESSION_MAX_MESSAGES,
    attach_audio_to_message,
    create_assistant_message,
    get_owned_session,
    handle_synthesis_error,
)

logger = logging.getLogger(__name__)


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
            400: OpenApiResponse(description="入力不正 / メッセージ件数上限"),
            401: OpenApiResponse(description="認証エラー"),
            404: OpenApiResponse(description="セッションまたは設定が見つからない"),
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
        content = in_serializer.validated_data["content"]

        try:
            config = TalkConfig.objects.select_related("system_prompt_ref").get(
                name=session.config_name
            )
        except TalkConfig.DoesNotExist:
            return Response(
                {"error": f"設定 '{session.config_name}' が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # DB 書き込みは atomic + select_for_update で同時 POST のレースを防ぐ。
        # ファイル書き込みは atomic 外に出して DB ロールバック時のオーファン
        # ファイルを発生させない。
        try:
            service = TalkService()
            assistant: ChatMessage | None = None
            audio_data: bytes | None = None
            audio_format: str = "wav"
            response_payload: dict
            with transaction.atomic():
                ChatSession.objects.select_for_update().get(id=session.id)
                existing = list(session.messages.values("role", "content", "sequence"))
                if len(existing) >= SESSION_MAX_MESSAGES:
                    return Response(
                        {
                            "error": (
                                "1 セッションのメッセージ数上限"
                                f"({SESSION_MAX_MESSAGES})に達しました"
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                next_seq = (max((m["sequence"] for m in existing), default=-1)) + 1
                api_messages = [
                    {"role": m["role"], "content": m["content"]} for m in existing
                ] + [{"role": "user", "content": content}]

                ChatMessage.objects.create(
                    session=session,
                    sequence=next_seq,
                    role="user",
                    content=content,
                )
                response_payload = service.synthesize_chat(
                    config=config,
                    messages=api_messages,
                    session_id=str(session.id),
                )
                assistant = create_assistant_message(
                    session=session,
                    sequence=next_seq + 1,
                    text=response_payload["message"]["content"],
                )
                audio_data = response_payload.get("audio_data")
                audio_format = response_payload.get("audio_format", "wav")
        except Exception as e:
            return handle_synthesis_error(
                e,
                fallback_message="チャット応答の生成中に問題が発生しました",
            )

        # commit 後にファイル書き込み（途中で失敗してもテキスト応答は残る）
        if audio_data and assistant is not None:
            attach_audio_to_message(assistant, audio_data, audio_format)

        # 初回応答後、title が空ならタイトル要約（失敗しても続行）
        if not session.title and session.messages.count() == 2:
            try:
                title = service.generate_session_title(
                    [
                        {"role": "user", "content": content},
                        {
                            "role": "assistant",
                            "content": response_payload["message"]["content"],
                        },
                    ],
                    session_id=str(session.id),
                )
                if title:
                    session.title = title
                    session.save(update_fields=["title", "updated_at"])
            except Exception:
                logger.exception("セッションタイトル生成に失敗")

        # updated_at を確実に進める
        session.save(update_fields=["updated_at"])

        out = ChatSessionDetailSerializer(session, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)


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
            200: OpenApiResponse(response=ChatSessionDetailSerializer),
            400: OpenApiResponse(description="入力不正 / assistant 編集不可"),
            401: OpenApiResponse(description="認証エラー"),
            404: OpenApiResponse(description="セッション/メッセージが見つからない"),
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
        new_content = in_serializer.validated_data["content"]

        try:
            config = TalkConfig.objects.select_related("system_prompt_ref").get(
                name=session.config_name
            )
        except TalkConfig.DoesNotExist:
            return Response(
                {"error": f"設定 '{session.config_name}' が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 対象以前の履歴のみで API を呼ぶ
        prior = list(
            session.messages.filter(sequence__lt=target.sequence)
            .order_by("sequence")
            .values("role", "content")
        )
        api_messages = [{"role": p["role"], "content": p["content"]} for p in prior] + [
            {"role": "user", "content": new_content}
        ]

        try:
            service = TalkService()
            assistant: ChatMessage | None = None
            audio_data: bytes | None = None
            audio_format: str = "wav"
            with transaction.atomic():
                ChatSession.objects.select_for_update().get(id=session.id)
                # 対象以降のメッセージは個別 delete でシグナルを確実に発火
                # （bulk delete でも現状シグナルは走るが将来の最適化に備える）
                for old in session.messages.filter(
                    sequence__gte=target.sequence
                ).order_by("-sequence"):
                    old.delete()
                ChatMessage.objects.create(
                    session=session,
                    sequence=target.sequence,
                    role="user",
                    content=new_content,
                )
                result = service.synthesize_chat(
                    config=config,
                    messages=api_messages,
                    session_id=str(session.id),
                )
                assistant = create_assistant_message(
                    session=session,
                    sequence=target.sequence + 1,
                    text=result["message"]["content"],
                )
                audio_data = result.get("audio_data")
                audio_format = result.get("audio_format", "wav")
        except Exception as e:
            return handle_synthesis_error(
                e,
                fallback_message="チャット応答の再生成中に問題が発生しました",
            )

        if audio_data and assistant is not None:
            attach_audio_to_message(assistant, audio_data, audio_format)

        session.save(update_fields=["updated_at"])

        out = ChatSessionDetailSerializer(session, context={"request": request})
        return Response(out.data, status=status.HTTP_200_OK)
