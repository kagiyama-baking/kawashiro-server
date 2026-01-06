"""Outlookアプリケーションのビュー"""

import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import authentication, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ms_graph.exceptions import AuthenticationError, ConfigurationError, NetworkError

from .exceptions import CalendarError
from .ms_graph_client import OutlookGraphClient
from .serializers import EventInfoSerializer, EventsQuerySerializer

# ロガーを設定
logger = logging.getLogger(__name__)


class OutlookEventsView(APIView):
    """Outlook Calendar予定取得ビュー"""

    # トークン認証を要求
    authentication_classes = (authentication.TokenAuthentication,)
    # 認証済みユーザーのみアクセス可能
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=["outlook"],
        summary="予定一覧取得",
        description=(
            "Outlook Calendarから予定一覧を取得します。\n\n"
            "日付範囲の指定方法:\n"
            "- デフォルト: 今日1日分の予定を取得\n"
            "- `days`を指定: start_dateからdays日分の予定を取得\n"
            "- `end_date`を指定: start_dateからend_dateまでの予定を取得\n\n"
            "※ `days`と`end_date`を同時に指定した場合は`end_date`が優先されます。"
        ),
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=str,
                location=OpenApiParameter.QUERY,
                description="取得開始日（YYYY-MM-DD形式、デフォルト: 今日）",
                required=False,
            ),
            OpenApiParameter(
                name="end_date",
                type=str,
                location=OpenApiParameter.QUERY,
                description="取得終了日（YYYY-MM-DD形式）",
                required=False,
            ),
            OpenApiParameter(
                name="days",
                type=int,
                location=OpenApiParameter.QUERY,
                description="取得日数（1-365、デフォルト: 1）",
                required=False,
            ),
        ],
        responses={
            200: {
                "description": "取得成功",
                "content": {
                    "application/json": {
                        "example": {
                            "start_date": "2025-12-23",
                            "end_date": "2025-12-23",
                            "count": 2,
                            "events": [
                                {
                                    "id": "AAMkAGI...",
                                    "subject": "チーム定例",
                                    "start": "2025-12-23T10:00:00+09:00",
                                    "end": "2025-12-23T11:00:00+09:00",
                                    "location": "会議室A",
                                    "is_all_day": False,
                                    "organizer": "user@example.com",
                                    "web_link": "https://outlook.office365.com/...",
                                    "body_preview": "議題: プロジェクト進捗...",
                                }
                            ],
                        }
                    }
                },
            },
            400: {"description": "入力データの検証エラー"},
            401: {"description": "認証が必要です"},
            500: {"description": "サーバーエラー"},
            502: {"description": "外部サービスとの通信エラー"},
            503: {"description": "サービス利用不可（設定エラー）"},
        },
    )
    def get(self, request, *args, **kwargs):
        """Outlook Calendarから予定一覧を取得"""
        serializer = EventsQuerySerializer(data=request.query_params)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_date = serializer.validated_data["start_date"]
        end_date = serializer.validated_data["end_date"]

        try:
            # Outlook Graph クライアントを作成
            client = OutlookGraphClient()

            # カレンダーイベントを取得
            events = client.get_calendar_events(
                start_date=start_date, end_date=end_date
            )

            # レスポンス形式に変換
            event_serializer = EventInfoSerializer(events, many=True)

            return Response(
                {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "count": len(events),
                    "events": event_serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except ConfigurationError as e:
            logger.error("設定エラー: %s", str(e))
            return Response(
                {
                    "error": "サービスの設定に問題があります。管理者にお問い合わせください。"
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except AuthenticationError as e:
            logger.error("認証エラー: %s", str(e))
            return Response(
                {
                    "error": "Outlookへの認証に失敗しました。管理者にお問い合わせください。"
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        except NetworkError as e:
            logger.error("ネットワークエラー: %s", str(e))
            return Response(
                {
                    "error": "Outlookへの接続に失敗しました。ネットワーク接続を確認して再試行してください。"
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except CalendarError as e:
            logger.warning("カレンダー取得エラー: %s", str(e))
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            logger.exception("予期しないエラー: %s", str(e))
            return Response(
                {
                    "error": "予定の取得中に問題が発生しました。しばらく待ってから再試行してください。"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
