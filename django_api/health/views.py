"""ヘルスチェックビュー"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """サーバーの死活監視用エンドポイント"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """サーバーが稼働中であることを返す"""
        return Response({"status": "ok"})
