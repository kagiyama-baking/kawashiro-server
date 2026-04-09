"""Views for weather app."""

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import authentication, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .client import WeatherClient
from .exceptions import (
    WeatherAreaNotFoundError,
    WeatherNetworkError,
    WeatherParseError,
    WeatherTimeoutError,
)
from .serializers import WeatherRequestSerializer, WeatherResponseSerializer


class WeatherForecastView(APIView):
    """Weather forecast API view."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=["weather"],
        summary="天気予報を取得",
        description="""天気予報API（tsukumijima.net経由）を利用して、指定した地域の天気予報を取得します。

## 予報区コード

6桁のコードで地域を指定します。予報区コードの例：
- `130010`: 東京都 東京地方
- `130020`: 東京都 伊豆諸島北部
- `140010`: 神奈川県 東部
- `270000`: 大阪府
- `400010`: 福岡県 福岡地方

## 取得可能データ

| day | 天気 | 気温 | 降水確率 |
|-----|------|------|----------|
| 0   | 今日 | 最低/最高 | 4時間ごと（4区分） |
| 1   | 明日 | 最低/最高 | 4時間ごと（4区分） |
| 2   | 明後日 | 最低/最高 | 4時間ごと（4区分） |
""",
        parameters=[
            OpenApiParameter(
                name="area_code",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="予報区コード（6桁）。例: 130010=東京地方, 270000=大阪府",
                examples=[
                    OpenApiExample("東京都 東京地方", value="130010"),
                    OpenApiExample("埼玉県 南部", value="110010"),
                    OpenApiExample("静岡県 西部", value="220040"),
                ],
            ),
            OpenApiParameter(
                name="day",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                default=0,
                description="予報日。0=今日, 1=明日, 2=明後日（デフォルト: 0）",
                examples=[
                    OpenApiExample("今日", value=0),
                    OpenApiExample("明日", value=1),
                    OpenApiExample("明後日", value=2),
                ],
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=WeatherResponseSerializer,
                description="天気予報データ",
            ),
            400: OpenApiResponse(
                description="バリデーションエラー（area_code未指定、day範囲外など）"
            ),
            401: OpenApiResponse(description="認証エラー（トークン未指定/無効）"),
            404: OpenApiResponse(
                description="予報区コードが見つからない（都道府県コードまたは地域コードが無効）"
            ),
            502: OpenApiResponse(
                description="天気予報APIへの接続エラーまたはレスポンス解析エラー"
            ),
            504: OpenApiResponse(description="天気予報APIへのリクエストタイムアウト"),
        },
    )
    def get(self, request):
        """Get weather forecast."""
        serializer = WeatherRequestSerializer(data=request.query_params)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        area_code = serializer.validated_data["area_code"]
        day = serializer.validated_data["day"]

        try:
            client = WeatherClient()
            weather_data = client.get_weather(area_code, day)
            response_serializer = WeatherResponseSerializer(weather_data)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except WeatherAreaNotFoundError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except WeatherTimeoutError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except (WeatherNetworkError, WeatherParseError) as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
