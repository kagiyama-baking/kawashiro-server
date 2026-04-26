"""ChatSession 一覧・作成・詳細・タイトル更新・削除 ビュー."""

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import authentication, generics, permissions, status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from ..models import ChatSession
from ..serializers import (
    ChatSessionCreateSerializer,
    ChatSessionDetailSerializer,
    ChatSessionListItemSerializer,
    ChatSessionUpdateSerializer,
)


class SessionPagination(LimitOffsetPagination):
    """セッション一覧のページネーション."""

    default_limit = 20
    max_limit = 100


class ChatSessionListCreateView(generics.GenericAPIView):
    """セッション一覧 / 新規作成."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = SessionPagination
    serializer_class = ChatSessionListItemSerializer
    renderer_classes = [JSONRenderer]

    def get_queryset(self):
        # annotate(Count/Sum) で GROUP BY が入ると Meta.ordering が効かなく
        # なる場合があるため、最新更新降順を明示する。
        return (
            ChatSession.objects.filter(user=self.request.user)
            .annotate(
                message_count=Count("messages"),
                total_audio_bytes=Coalesce(Sum("messages__audio_size_bytes"), 0),
            )
            .order_by("-updated_at", "-created_at")
        )

    @extend_schema(
        tags=["talk"],
        summary="チャットセッション一覧を取得",
        responses={200: OpenApiResponse(response=ChatSessionListItemSerializer)},
    )
    def get(self, request, *args, **kwargs):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["talk"],
        summary="新しいチャットセッションを作成",
        request=ChatSessionCreateSerializer,
        responses={
            201: OpenApiResponse(response=ChatSessionDetailSerializer),
            400: OpenApiResponse(description="config_name 不正"),
            401: OpenApiResponse(description="認証エラー"),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = ChatSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = ChatSession.objects.create(
            user=request.user,
            config_name=serializer.validated_data["config_name"],
        )
        out = ChatSessionDetailSerializer(session, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class ChatSessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """セッション詳細 / タイトル更新 / 削除."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]
    lookup_url_kwarg = "session_id"
    lookup_field = "id"
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ChatSessionUpdateSerializer
        return ChatSessionDetailSerializer

    @extend_schema(tags=["talk"], summary="セッション詳細（メッセージ含む）")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=["talk"],
        summary="セッションのタイトルを更新",
        request=ChatSessionUpdateSerializer,
        responses={200: OpenApiResponse(response=ChatSessionDetailSerializer)},
    )
    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ChatSessionUpdateSerializer(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        out = ChatSessionDetailSerializer(instance, context={"request": request})
        return Response(out.data)

    @extend_schema(tags=["talk"], summary="セッションを削除（音声ファイルも物理削除）")
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)
