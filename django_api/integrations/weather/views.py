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

from .exceptions import (
    JMAAreaNotFoundError,
    JMANetworkError,
    JMAParseError,
    JMATimeoutError,
)
from .jma_client import JMAWeatherClient
from .serializers import WeatherRequestSerializer, WeatherResponseSerializer


class WeatherForecastView(APIView):
    """Weather forecast API view."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=["weather"],
        summary="天気予報を取得",
        description="""気象庁の天気予報APIを利用して、指定した地域の天気予報を取得します。

## 予報区コード

6桁のコードで地域を指定します。予報区コードの例：
- `130010`: 東京都 東京地方
- `130020`: 東京都 伊豆諸島北部
- `140010`: 神奈川県 東部
- `270000`: 大阪府
- `400010`: 福岡県 福岡地方

詳細は[気象庁の地域コード一覧](https://www.jma.go.jp/bosai/common/const/area.json)を参照。

## 特殊仕様

### 深夜帯のデータ調整（0:00〜5:00 JST）

気象庁APIは5:00/11:00/17:00頃に更新されるため、深夜帯は前日のデータが返されます。
このAPIでは自動的にインデックスを調整し、正しい日付のデータを返します：

| day | 通常時（5:00〜23:59） | 深夜帯（0:00〜4:59） |
|-----|---------------------|---------------------|
| 0   | 当日の予報           | 翌日の予報（=実際の今日） |
| 1   | 翌日の予報           | 翌々日の予報（=実際の明日） |
| 2   | 翌々日の予報         | 週間予報から取得 |

### データソース

| day | 天気 | 気温 | 降水確率 |
|-----|------|------|----------|
| 0   | 短期予報 | 取得不可 | 18時〜24時のみ |
| 1   | 短期予報 | 短期予報 | 4時間ごと（4区分） |
| 2   | 短期予報 | 週間予報 | 週間予報（1日1値、全時間帯同値） |
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
                description="気象庁APIへの接続エラーまたはレスポンス解析エラー"
            ),
            504: OpenApiResponse(description="気象庁APIへのリクエストタイムアウト"),
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
            client = JMAWeatherClient()
            weather_data = client.get_weather(area_code, day)
            response_serializer = WeatherResponseSerializer(weather_data)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except JMAAreaNotFoundError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except JMATimeoutError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except (JMANetworkError, JMAParseError) as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
