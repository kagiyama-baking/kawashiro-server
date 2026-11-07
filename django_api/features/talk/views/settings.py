"""Talk 設定の一覧ビュー（フロントの Talk で選べる設定とシーン）."""

from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import authentication, permissions
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.llm.models import AgentSkill

from ..models import TalkSetting
from ..serializers import TalkSettingListResponseSerializer


class TalkSettingsListView(APIView):
    """有効な Talk 設定と、それぞれで選べる有効なシーン."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["talk"],
        summary="Talk 設定の一覧を取得（有効な設定と、選べるシーン）",
        responses={
            200: OpenApiResponse(response=TalkSettingListResponseSerializer),
            401: OpenApiResponse(description="認証エラー"),
        },
    )
    def get(self, request):
        settings = (
            TalkSetting.objects.filter(is_enabled=True)
            .prefetch_related(
                Prefetch(
                    "skills",
                    queryset=AgentSkill.objects.filter(is_enabled=True).order_by(
                        "name"
                    ),
                    to_attr="enabled_skills",
                )
            )
            .order_by("name")
        )
        serializer = TalkSettingListResponseSerializer({"settings": settings})
        return Response(serializer.data)
