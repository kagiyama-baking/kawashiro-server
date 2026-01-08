"""Views for train diainfo API."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import authentication, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from train.exceptions import (
    YahooNetworkError,
    YahooParseError,
    YahooRailNotFoundError,
    YahooTimeoutError,
)
from train.serializers import DiainfoRequestSerializer, DiainfoResponseSerializer
from train.yahoo_client import YahooTransitClient


class DiainfoView(APIView):
    """路線の運行情報を取得するAPI"""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=["train"],
        summary="路線運行情報を取得",
        description="Yahoo!乗換案内から指定された路線の運行情報を取得します。複数の路線IDをカンマ区切りで指定できます。",
        parameters=[
            OpenApiParameter(
                name="rail_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                description="路線ID（複数の場合はカンマ区切り。例: 131,22,35）",
                required=True,
            ),
        ],
        responses={200: DiainfoResponseSerializer(many=True)},
    )
    def get(self, request):
        """運行情報を取得する"""
        serializer = DiainfoRequestSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        rail_ids = serializer.validated_data["rail_ids"]

        try:
            client = YahooTransitClient()
            results = client.fetch_multiple_diainfo(rail_ids)
            response_serializer = DiainfoResponseSerializer(results, many=True)
            return Response(response_serializer.data)

        except YahooRailNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except YahooTimeoutError as e:
            return Response({"error": str(e)}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except (YahooNetworkError, YahooParseError) as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
