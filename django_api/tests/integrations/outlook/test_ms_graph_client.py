"""OutlookGraphClientのテスト"""

from datetime import date
from unittest.mock import Mock, patch
from urllib.parse import parse_qsl, urlsplit

import pytest
import requests

from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.outlook.exceptions import CalendarError

CALENDAR_VIEW_URL = (
    "https://graph.microsoft.com/v1.0/users/test@example.com/calendar/calendarView"
)


def _empty_response(status_code: int) -> Mock:
    """イベント 0 件を返す応答のモック"""
    response = Mock(status_code=status_code)
    response.json.return_value = {"value": []}
    return response


def _sent_requests(
    client, start_date: date, end_date: date, *statuses: int
) -> list[requests.PreparedRequest]:
    """Session.send を差し替えて予定を取得し、requests が組み立てた送信リクエストを返す

    statuses は呼び出し順に返す応答のステータスコード。
    """
    responses = [_empty_response(status) for status in statuses]

    with patch.object(client._session, "send", side_effect=responses) as mock_send:
        client.get_calendar_events(start_date=start_date, end_date=end_date)

    return [call.args[0] for call in mock_send.call_args_list]


def _decoded_query(sent: requests.PreparedRequest) -> dict[str, str]:
    """送信 URL のクエリをフォームの規則でデコードする（生の「+」は空白になる）"""
    return dict(parse_qsl(urlsplit(sent.url).query))


@pytest.fixture
def mock_outlook_graph_settings():
    """OutlookGraphSettings用のモックフィクスチャ"""
    from integrations.msgraph.config import MSGraphSettings

    settings = MSGraphSettings(
        tenant_id="test-tenant",
        client_id="test-client",
        cert_thumbprint="test-thumb",
        private_key="-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----",
        target_user="test@example.com",
    )

    with patch(
        "integrations.msgraph.base.get_ms_graph_settings", return_value=settings
    ):
        yield settings


@pytest.fixture
def outlook_client(mock_outlook_graph_settings):
    """モック設定を使用したOutlookMSGraphClientのフィクスチャ"""
    from integrations.msgraph import OutlookMSGraphClient

    client = OutlookMSGraphClient()
    client._access_token = "test-token"
    return client


class TestOutlookMSGraphClientInit:
    """OutlookMSGraphClientの初期化テスト"""

    def test_init_success(self, mock_outlook_graph_settings):
        """正常に初期化できること"""
        from integrations.msgraph import OutlookMSGraphClient

        client = OutlookMSGraphClient()

        assert client.tenant_id == "test-tenant"
        assert client.client_id == "test-client"
        assert client.target_user == "test@example.com"

    def test_init_with_configuration_error(self):
        """設定エラー時に ConfigurationError が発生すること"""
        from integrations.msgraph import OutlookMSGraphClient

        with (
            patch(
                "integrations.msgraph.base.get_ms_graph_settings",
                side_effect=ConfigurationError("Missing config"),
            ),
            pytest.raises(ConfigurationError),
        ):
            OutlookMSGraphClient()


class TestGetCalendarEvents:
    """get_calendar_eventsメソッドのテスト"""

    @pytest.mark.parametrize(
        "api_value, expected_count",
        [
            pytest.param(
                [
                    {
                        "id": "event-123",
                        "subject": "テスト会議",
                        "start": {
                            "dateTime": "2025-12-23T10:00:00",
                            "timeZone": "Asia/Tokyo",
                        },
                        "end": {
                            "dateTime": "2025-12-23T11:00:00",
                            "timeZone": "Asia/Tokyo",
                        },
                        "isAllDay": False,
                    }
                ],
                1,
                id="one_event",
            ),
            pytest.param([], 0, id="empty"),
        ],
    )
    def test_get_events_success(self, outlook_client, api_value, expected_count):
        """カレンダーイベント取得（正常系）"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": api_value}
        mock_response.raise_for_status = Mock()

        with patch.object(
            outlook_client._session, "get", return_value=mock_response
        ) as mock_get:
            events = outlook_client.get_calendar_events(
                start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
            )

            assert len(events) == expected_count
            mock_get.assert_called_once()
            if expected_count:
                assert events[0]["subject"] == "テスト会議"

    @pytest.mark.parametrize(
        "side_effect, expected_msg",
        [
            pytest.param(
                requests.exceptions.Timeout("Timeout"),
                "タイムアウト",
                id="timeout",
            ),
            pytest.param(
                requests.exceptions.ConnectionError("Connection refused"),
                "接続に失敗",
                id="connection_error",
            ),
        ],
    )
    def test_get_events_network_errors(self, outlook_client, side_effect, expected_msg):
        """ネットワーク系エラー時に NetworkError を発生させること"""
        with patch.object(outlook_client._session, "get", side_effect=side_effect):
            with pytest.raises(NetworkError) as exc_info:
                outlook_client.get_calendar_events(
                    start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
                )

            assert expected_msg in str(exc_info.value)

    @pytest.mark.parametrize(
        "status_code, expected_exc",
        [
            (401, AuthenticationError),
            (500, CalendarError),
        ],
        ids=["unauthorized", "server_error"],
    )
    def test_get_events_http_errors(self, outlook_client, status_code, expected_exc):
        """HTTP エラー時に対応する例外を発生させること"""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        with (
            patch.object(outlook_client._session, "get", return_value=mock_response),
            pytest.raises(expected_exc),
        ):
            outlook_client.get_calendar_events(
                start_date=date(2025, 12, 23), end_date=date(2025, 12, 23)
            )


@pytest.mark.unit
class TestGetCalendarEventsDateRange:
    """calendarView に渡す期間（startDateTime / endDateTime）のテスト

    Graph はオフセットのない日時を UTC として解釈する。ローカルの暦日で
    予定を取るには、期間の両端を Django の現在のタイムゾーンでの 0 時として
    オフセット付きで送る必要がある。
    """

    @pytest.mark.parametrize(
        "start_date, end_date, expected_start, expected_end",
        [
            pytest.param(
                date(2026, 11, 4),
                date(2026, 11, 4),
                "2026-11-04T00:00:00+09:00",
                "2026-11-05T00:00:00+09:00",
                id="single_day",
            ),
            pytest.param(
                date(2026, 11, 4),
                date(2026, 11, 6),
                "2026-11-04T00:00:00+09:00",
                "2026-11-07T00:00:00+09:00",
                id="multi_day",
            ),
        ],
    )
    def test_get_calendar_events_with_date_range_sends_local_midnights_with_offset(
        self, outlook_client, start_date, end_date, expected_start, expected_end
    ):
        """開始日の 0 時から終了日の翌日 0 時までを、オフセット付きで送ること"""
        (sent,) = _sent_requests(outlook_client, start_date, end_date, 200)

        query = _decoded_query(sent)
        assert query["startDateTime"] == expected_start
        assert query["endDateTime"] == expected_end

    def test_get_calendar_events_with_positive_offset_percent_encodes_plus(
        self, outlook_client
    ):
        """オフセットの「+」を %2B にエンコードして送ること（生の「+」は空白と解釈される）"""
        (sent,) = _sent_requests(
            outlook_client, date(2026, 11, 4), date(2026, 11, 4), 200
        )

        assert "startDateTime=2026-11-04T00%3A00%3A00%2B09%3A00" in sent.url
        assert "endDateTime=2026-11-05T00%3A00%3A00%2B09%3A00" in sent.url

    def test_get_calendar_events_with_date_range_keeps_endpoint_select_and_orderby(
        self, outlook_client
    ):
        """送り先の calendarView と $select / $orderby は従来どおりであること"""
        (sent,) = _sent_requests(
            outlook_client, date(2026, 11, 4), date(2026, 11, 4), 200
        )

        assert sent.url.startswith(f"{CALENDAR_VIEW_URL}?")
        query = _decoded_query(sent)
        assert query["$select"] == (
            "id,subject,start,end,location,isAllDay,organizer,webLink,bodyPreview"
        )
        assert query["$orderby"] == "start/dateTime"

    def test_get_calendar_events_on_401_retries_with_same_range(self, outlook_client):
        """401 でトークンを取り直した再試行でも、同じ期間を送ること"""
        with patch.object(outlook_client, "acquire_token") as mock_acquire_token:
            first, retry = _sent_requests(
                outlook_client, date(2026, 11, 4), date(2026, 11, 4), 401, 200
            )

        mock_acquire_token.assert_called_once()
        assert retry.url == first.url
        query = _decoded_query(retry)
        assert query["startDateTime"] == "2026-11-04T00:00:00+09:00"
        assert query["endDateTime"] == "2026-11-05T00:00:00+09:00"

    @pytest.mark.parametrize(
        "time_zone, start_date, expected_start, expected_end",
        [
            pytest.param(
                "UTC",
                date(2026, 11, 4),
                "2026-11-04T00:00:00+00:00",
                "2026-11-05T00:00:00+00:00",
                id="utc",
            ),
            # 2026-11-01 02:00 に夏時間が終わるため、両端でオフセットが異なる
            pytest.param(
                "America/New_York",
                date(2026, 11, 1),
                "2026-11-01T00:00:00-04:00",
                "2026-11-02T00:00:00-05:00",
                id="dst_ends_within_range",
            ),
        ],
    )
    def test_get_calendar_events_with_other_time_zone_follows_its_offsets(
        self,
        outlook_client,
        settings,
        time_zone,
        start_date,
        expected_start,
        expected_end,
    ):
        """オフセットは TIME_ZONE 設定に従い、両端それぞれの時点で決まること"""
        settings.TIME_ZONE = time_zone

        (sent,) = _sent_requests(outlook_client, start_date, start_date, 200)

        query = _decoded_query(sent)
        assert query["startDateTime"] == expected_start
        assert query["endDateTime"] == expected_end


class TestAcquireToken:
    """acquire_tokenメソッドのテスト"""

    def test_acquire_token_success(self, outlook_client):
        """トークンを正常に取得できること"""
        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "new-test-token"
        }

        with patch(
            "integrations.msgraph.base.ConfidentialClientApplication",
            return_value=mock_app,
        ):
            token = outlook_client.acquire_token()

            assert token == "new-test-token"
            assert outlook_client._access_token == "new-test-token"

    def test_acquire_token_failure(self, outlook_client):
        """トークン取得失敗時に AuthenticationError を発生させること"""
        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "Invalid client credentials",
        }

        with patch(
            "integrations.msgraph.base.ConfidentialClientApplication",
            return_value=mock_app,
        ):
            with pytest.raises(AuthenticationError) as exc_info:
                outlook_client.acquire_token()

            assert "Invalid client credentials" in str(exc_info.value)
