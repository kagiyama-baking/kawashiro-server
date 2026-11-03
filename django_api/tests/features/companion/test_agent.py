"""Companion エージェントと常設ツール（日時・天気・今日の予定）のテスト.

モデルは台本（`ScriptedLLM`）で差し替え、ツールの呼び出しから結果がモデルに届くまでを
`run_agent_sync` で通す。祝日・天気・Graph のクライアントは差し替えるので外へは出ない。
"""

import json
import logging
import threading
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
import requests
from pydantic_ai.capabilities import Capability
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolReturnPart
from pydantic_ai.profiles import ModelProfileSpec

from features.companion.agent import COMPANION_AGENT, CompanionDeps, response_policy
from integrations.holiday import HolidayNetworkError, HolidayTimeoutError
from integrations.llm.runtime import _LITELLM_PROFILE, run_agent_sync
from integrations.msgraph.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)
from integrations.outlook.exceptions import CalendarError
from integrations.weather.exceptions import (
    WeatherAPIError,
    WeatherAreaNotFoundError,
    WeatherNetworkError,
    WeatherParseError,
    WeatherTimeoutError,
)
from tests.fixtures.llm import (
    RecordedRequest,
    ScriptedLLM,
    load_capability,
    make_llm_settings,
    tool_call,
)

pytestmark = pytest.mark.unit

AGENT_LOGGER = "features.companion.agent"
AREA_CODE = "130010"

# ツール名・説明・引数は Langfuse 上のスキル本文との契約（変えるときはスキル本文も直す）
TOOL_DESCRIPTIONS = {
    "get_datetime": (
        "現在の日付・時刻・曜日と、今日が祝日ならその名前を返す。\n\n"
        "祝日を確認できなかったときは holiday_name が null、"
        "holiday_lookup_failed が true になる。"
    ),
    "get_weather": (
        "設定された地域の天気予報（天気・最高/最低気温・6 時間ごとの降水確率）を返す。"
    ),
    "get_today_events": (
        "今日の予定（件名・開始/終了時刻・終日かどうか・場所）を開始時刻の順に返す。"
    ),
}
TOOL_PARAMETERS = {
    "get_datetime": {},
    "get_weather": {
        "day": {
            "default": 0,
            "description": "予報日。0=今日、1=明日、2=明後日",
            "enum": [0, 1, 2],
            "type": "integer",
        }
    },
    "get_today_events": {},
}

# 天気予報クライアントの結果（`WeatherClient.get_weather` の形）
FORECAST = {
    "area_name": "東京都 東京地方",
    "area_code": AREA_CODE,
    "date": "2026-11-04",
    "weather": "晴れ　夜　くもり",
    "weather_code": "101",
    "temp_min": 9,
    "temp_max": 18,
    "pop_00_06": None,
    "pop_06_12": 10,
    "pop_12_18": 20,
    "pop_18_24": 30,
}

WEATHER_ERROR = {"error": "天気予報を取得できませんでした"}
EVENTS_ERROR = {"error": "今日の予定を取得できませんでした"}


def _graph_event(**fields) -> dict:
    """Graph の calendarView が返す予定（`Prefer: outlook.timezone="Asia/Tokyo"` の形）."""
    return {
        "id": "AAMkAD-event",
        "subject": "定例ミーティング",
        "start": {"dateTime": "2026-11-04T09:00:00.0000000", "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": "2026-11-04T10:30:00.0000000", "timeZone": "Asia/Tokyo"},
        "location": {"displayName": "会議室A", "locationType": "default"},
        "isAllDay": False,
        "organizer": {
            "emailAddress": {"name": "主催者", "address": "organizer@example.com"}
        },
        "webLink": "https://outlook.office365.com/owa/?itemid=AAMkAD-event",
        "bodyPreview": "議題: 社外秘の内容",
        **fields,
    }


def _graph_event_without(key: str) -> dict:
    """項目 `key` そのものがない予定."""
    return {name: value for name, value in _graph_event().items() if name != key}


def _run(
    *script: str | ModelResponse,
    area_code: str = AREA_CODE,
    profile: ModelProfileSpec | None = None,
    **run_options,
) -> ScriptedLLM:
    """台本どおりに COMPANION_AGENT を 1 回実行し、受け取った内容を記録した代役を返す."""
    llm = ScriptedLLM(*script, profile=profile)
    with COMPANION_AGENT.override(model=llm.model):
        run_agent_sync(
            COMPANION_AGENT,
            make_llm_settings("companion"),
            user_prompt="おはよう",
            deps=CompanionDeps(area_code=area_code),
            **run_options,
        )
    return llm


def _tool_returns(request: RecordedRequest) -> list[ToolReturnPart]:
    """リクエストに含まれるツールの戻り値を順に返す."""
    return [
        part
        for message in request.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


def _call(step: ModelResponse, *, area_code: str = AREA_CODE) -> dict:
    """ツールを 1 回呼ばせて、モデルに届いた結果（JSON）を辞書で返す."""
    llm = _run(step, "結論", area_code=area_code)
    (returned,) = _tool_returns(llm.requests[1])
    return json.loads(returned.content)


def _recording(threads: list[int], value):
    """呼ばれたスレッドを `threads` に記録して `value` を返す side_effect を作る."""

    def record(*args, **kwargs):
        threads.append(threading.get_ident())
        return value

    return record


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """エージェントのモジュールが出した warning のメッセージを返す."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == AGENT_LOGGER and record.levelno == logging.WARNING
    ]


@pytest.fixture
def fixed_clock():
    """日時情報の現在時刻を 2026-11-03（火・文化の日）07:30:00 に固定する."""
    with patch("integrations.holiday.datetime_info.datetime") as mocked:
        mocked.now.return_value = datetime(2026, 11, 3, 7, 30, 0)
        yield mocked


@pytest.fixture
def fixed_today():
    """Django の現在時刻を 2026-11-03 15:30 UTC（日本時間では 11-04 の 00:30）に固定する."""
    with patch(
        "django.utils.timezone.now",
        return_value=datetime(2026, 11, 3, 15, 30, tzinfo=UTC),
    ):
        yield date(2026, 11, 4)


@pytest.fixture
def holiday_client():
    """祝日 API のクライアントを差し替える（既定は祝日なし）."""
    with patch("features.companion.agent.HolidayClient", autospec=True) as cls:
        cls.return_value.get_holiday_name.return_value = None
        yield cls.return_value


@pytest.fixture
def weather_client():
    """天気予報のクライアントを差し替える（既定は FORECAST を返す）."""
    with patch("features.companion.agent.WeatherClient", autospec=True) as cls:
        cls.return_value.get_weather.return_value = FORECAST
        yield cls.return_value


@pytest.fixture
def outlook_client():
    """Graph（Outlook の予定）のクライアントを差し替える（既定は予定なし）."""
    with patch("features.companion.agent.OutlookMSGraphClient", autospec=True) as cls:
        cls.return_value.get_calendar_events.return_value = []
        yield cls.return_value


class TestCompanionAgent:
    """エージェントそのものとツールの契約."""

    def test_tools_names_descriptions_and_parameters_match_skill_contract(self):
        """ツール名・説明・引数は Langfuse のスキル本文との契約なので変えない."""
        llm = _run("結論")

        tools = {tool.name: tool for tool in llm.requests[0].function_tools}
        assert {name: tool.description for name, tool in tools.items()} == (
            TOOL_DESCRIPTIONS
        )
        assert {
            name: tool.parameters_json_schema["properties"]
            for name, tool in tools.items()
        } == TOOL_PARAMETERS

    def test_agent_without_own_instructions_sends_only_run_instructions(self):
        """エージェント自身は指示を持たない（キャラクター設定と方針は実行ごとに渡す）."""
        llm = _run("結論", instructions="キャラクター設定")

        assert llm.requests[0].system_prompts == ["キャラクター設定"]

    def test_agent_with_empty_response_returns_none_without_retry(self):
        """本文のない応答は再試行せず None として受け取る（空かどうかはサービスが判断する）."""
        llm = ScriptedLLM(ModelResponse(parts=[TextPart(content="")]))

        with COMPANION_AGENT.override(model=llm.model):
            result = run_agent_sync(
                COMPANION_AGENT,
                make_llm_settings("companion"),
                user_prompt="おはよう",
                deps=CompanionDeps(area_code=AREA_CODE),
            )

        assert result.output is None
        assert len(llm.requests) == 1

    def test_tools_after_skill_is_loaded_stay_available_and_skill_is_system(
        self, weather_client
    ):
        """スキル（遅延 capability）を読み込んでもツールを使え、本文は system で届く.

        本番のプロファイルでは読み込んだ本文が会話途中の system になり、ユーザーの発話に混ざらない。
        """
        skill = Capability(
            id="good-morning",
            description="朝のあいさつ",
            instructions="天気に触れて挨拶する",
            defer_loading=True,
        )

        llm = _run(
            load_capability("good-morning"),
            tool_call("get_weather"),
            "おはよう！",
            profile=_LITELLM_PROFILE,
            capabilities=[skill],
        )

        for request in llm.requests:
            names = {tool.name for tool in request.function_tools}
            assert {"get_datetime", "get_weather", "get_today_events"} <= names
        assert llm.requests[1].system_prompts[-1] == (
            '<context id="capability:good-morning">\n天気に触れて挨拶する\n</context>'
        )
        assert llm.requests[2].user_prompt == "おはよう"
        weather_client.get_weather.assert_called_once_with(AREA_CODE, 0)

    @pytest.mark.parametrize(
        ("tool_name", "client_path"),
        [
            ("get_datetime", "features.companion.agent.HolidayClient"),
            ("get_weather", "features.companion.agent.WeatherClient"),
            ("get_today_events", "features.companion.agent.OutlookMSGraphClient"),
        ],
    )
    def test_tool_builds_and_calls_client_on_calling_thread(
        self, tool_name, client_path
    ):
        """ツールの同期部分（クライアントの生成と呼び出し）は呼び出し元のスレッドで動く.

        Graph のクライアントは生成時に DB の設定を読むので、呼び出し元の DB 接続
        （トランザクションの中のデータ）を使うための前提になる。
        """
        threads: list[int] = []
        client = MagicMock()
        client.get_holiday_name.side_effect = _recording(threads, None)
        client.get_weather.side_effect = _recording(threads, FORECAST)
        client.get_calendar_events.side_effect = _recording(threads, [])

        with patch(client_path, side_effect=_recording(threads, client)):
            _run(tool_call(tool_name), "結論")

        assert threads == [threading.get_ident()] * 2

    @pytest.mark.parametrize(
        ("tool_name", "client_path", "method"),
        [
            (
                "get_datetime",
                "features.companion.agent.HolidayClient",
                "get_holiday_name",
            ),
            ("get_weather", "features.companion.agent.WeatherClient", "get_weather"),
            (
                "get_today_events",
                "features.companion.agent.OutlookMSGraphClient",
                "get_calendar_events",
            ),
        ],
    )
    def test_tool_with_unexpected_error_fails_run(self, tool_name, client_path, method):
        """想定外の例外は error にせず、実行ごと失敗させる（不具合を隠さない）."""
        with patch(client_path) as cls:
            getattr(cls.return_value, method).side_effect = RuntimeError("bug")

            with pytest.raises(RuntimeError, match="bug"):
                _run(tool_call(tool_name), "結論")


class TestGetDatetime:
    """get_datetime（日付・時刻・曜日・祝日）."""

    def test_get_datetime_on_holiday_returns_date_time_weekday_and_holiday_name(
        self, fixed_clock, holiday_client
    ):
        """日付・時刻・曜日・祝日名の 5 項目を返し、失敗の印は付けない."""
        holiday_client.get_holiday_name.return_value = "文化の日"

        result = _call(tool_call("get_datetime"))

        assert result == {
            "date": "2026-11-03",
            "time": "07:30:00",
            "day_of_week": "Tuesday",
            "day_of_week_ja": "火曜日",
            "holiday_name": "文化の日",
        }
        holiday_client.get_holiday_name.assert_called_once_with("2026-11-03")

    @pytest.mark.parametrize(
        "error",
        [
            HolidayNetworkError("祝日APIへの接続に失敗しました"),
            HolidayTimeoutError("祝日APIへのリクエストがタイムアウトしました"),
        ],
    )
    def test_get_datetime_when_holiday_lookup_fails_keeps_date_and_time(
        self, fixed_clock, holiday_client, caplog, error
    ):
        """祝日を確認できなくても日付と時刻は返し、祝日名は null・失敗の印を付ける."""
        holiday_client.get_holiday_name.side_effect = error

        result = _call(tool_call("get_datetime"))

        assert result == {
            "date": "2026-11-03",
            "time": "07:30:00",
            "day_of_week": "Tuesday",
            "day_of_week_ja": "火曜日",
            "holiday_name": None,
            "holiday_lookup_failed": True,
        }
        (message,) = _warnings(caplog)
        assert str(error) in message


class TestGetWeather:
    """get_weather（設定された地域の天気予報）."""

    def test_get_weather_uses_area_code_from_deps_and_given_day(self, weather_client):
        """地域は依存（設定）から、日はモデルの引数から取り、結果はそのまま返す."""
        llm = _run(tool_call("get_weather", day=1), "結論")

        weather_client.get_weather.assert_called_once_with(AREA_CODE, 1)
        (returned,) = _tool_returns(llm.requests[1])
        assert json.loads(returned.content) == FORECAST
        assert "東京都 東京地方" in returned.content  # ensure_ascii=False のまま

    def test_get_weather_without_day_returns_today(self, weather_client):
        """日を省略すると今日（0）の予報を返す."""
        _call(tool_call("get_weather"))

        weather_client.get_weather.assert_called_once_with(AREA_CODE, 0)

    def test_get_weather_with_empty_area_code_returns_error_without_request(
        self, weather_client
    ):
        """予報区コードが空なら天気予報 API を呼ばずに error を返す."""
        result = _call(tool_call("get_weather"), area_code="")

        assert result == {"error": "天気の地域が設定されていません"}
        weather_client.get_weather.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            WeatherAreaNotFoundError("地域コード '130010' が見つかりません"),
            WeatherNetworkError("天気予報APIへの接続に失敗しました"),
            WeatherTimeoutError("天気予報APIへのリクエストがタイムアウトしました"),
            WeatherParseError("予報日 2 は範囲外です（0〜1）"),
            WeatherAPIError("天気予報APIのエラー"),
        ],
    )
    def test_get_weather_when_client_fails_returns_error(
        self, weather_client, caplog, error
    ):
        """天気予報の失敗は warning を出して error を返し、実行は続ける."""
        weather_client.get_weather.side_effect = error

        result = _call(tool_call("get_weather"))

        assert result == WEATHER_ERROR
        (message,) = _warnings(caplog)
        assert str(error) in message

    def test_get_weather_with_day_out_of_range_asks_model_to_retry(
        self, weather_client
    ):
        """0〜2 以外の日は引数の検証で弾き、クライアントを呼ばずにモデルへ再試行を求める."""
        llm = _run(
            tool_call("get_weather", day=3), tool_call("get_weather", day=2), "結論"
        )

        rejected, accepted = _tool_returns(llm.requests[2])
        assert rejected.outcome == "retried"
        assert accepted.outcome == "success"
        weather_client.get_weather.assert_called_once_with(AREA_CODE, 2)


class TestGetTodayEvents:
    """get_today_events（Outlook の今日の予定）."""

    def test_get_today_events_returns_only_summary_fields(
        self, fixed_today, outlook_client
    ):
        """件名・開始/終了（HH:MM）・終日・場所だけを返す（本文の抜粋・主催者・リンクは渡さない）."""
        outlook_client.get_calendar_events.return_value = [_graph_event()]

        llm = _run(tool_call("get_today_events"), "結論")

        (returned,) = _tool_returns(llm.requests[1])
        assert json.loads(returned.content) == {
            "date": "2026-11-04",
            "events": [
                {
                    "subject": "定例ミーティング",
                    "start": "09:00",
                    "end": "10:30",
                    "is_all_day": False,
                    "location": "会議室A",
                }
            ],
        }
        assert "会議室A" in returned.content  # ensure_ascii=False のまま

    def test_get_today_events_with_all_day_event_returns_null_times_in_order(
        self, fixed_today, outlook_client
    ):
        """終日の予定は開始・終了を null にし、予定は Graph の順（開始時刻の順）のまま返す."""
        outlook_client.get_calendar_events.return_value = [
            _graph_event(
                subject="休暇",
                isAllDay=True,
                start={"dateTime": "2026-11-04T00:00:00.0000000"},
                end={"dateTime": "2026-11-05T00:00:00.0000000"},
            ),
            _graph_event(subject="定例ミーティング"),
        ]

        result = _call(tool_call("get_today_events"))

        assert [event["subject"] for event in result["events"]] == [
            "休暇",
            "定例ミーティング",
        ]
        assert result["events"][0] == {
            "subject": "休暇",
            "start": None,
            "end": None,
            "is_all_day": True,
            "location": "会議室A",
        }

    @pytest.mark.parametrize(
        "event",
        [
            _graph_event(location={"displayName": ""}),
            _graph_event(location={}),
            _graph_event(location=None),
            _graph_event_without("location"),
        ],
        ids=["empty-name", "no-name", "null", "no-location"],
    )
    def test_get_today_events_without_location_returns_empty_location(
        self, fixed_today, outlook_client, event
    ):
        """場所がない予定は空文字にする."""
        outlook_client.get_calendar_events.return_value = [event]

        result = _call(tool_call("get_today_events"))

        assert result["events"][0]["location"] == ""

    @pytest.mark.parametrize(
        "event",
        [
            _graph_event(start={"dateTime": "2026-11-04 朝"}),
            _graph_event(start={"dateTime": ""}),
            _graph_event(start=None),
            _graph_event_without("start"),
        ],
        ids=["unreadable", "empty", "null", "no-start"],
    )
    def test_get_today_events_with_unreadable_start_returns_null_start(
        self, fixed_today, outlook_client, event
    ):
        """開始時刻が読めない予定も落とさず、開始だけ null にする（終日とは区別できる）."""
        outlook_client.get_calendar_events.return_value = [event]

        result = _call(tool_call("get_today_events"))

        assert result["events"][0] == {
            "subject": "定例ミーティング",
            "start": None,
            "end": "10:30",
            "is_all_day": False,
            "location": "会議室A",
        }

    def test_get_today_events_queries_today_in_django_timezone(
        self, fixed_today, outlook_client
    ):
        """「今日」は Django のタイムゾーンで決め、開始日・終了日とも今日で取る.

        現在は UTC では 11-03 だが、日本時間（TIME_ZONE）では 11-04。
        """
        result = _call(tool_call("get_today_events"))

        outlook_client.get_calendar_events.assert_called_once_with(
            fixed_today, fixed_today
        )
        assert result == {"date": "2026-11-04", "events": []}

    def test_get_today_events_without_msgraph_config_returns_error(self, caplog):
        """Graph の設定がない（クライアントの生成で失敗する）ときは error を返す."""
        with patch(
            "features.companion.agent.OutlookMSGraphClient",
            side_effect=ConfigurationError("有効なMicrosoft Graph API設定がありません"),
        ):
            result = _call(tool_call("get_today_events"))

        assert result == EVENTS_ERROR
        (message,) = _warnings(caplog)
        assert "有効なMicrosoft Graph API設定がありません" in message

    @pytest.mark.parametrize(
        "error",
        [
            AuthenticationError("認証に失敗しました"),
            NetworkError("Outlookへの接続に失敗しました"),
            CalendarError("カレンダーイベントの取得に失敗しました"),
            # msal のトークン取得の通信エラーは requests の例外のまま届く
            requests.ConnectionError("login.microsoftonline.com に接続できません"),
        ],
    )
    def test_get_today_events_when_fetch_fails_returns_error(
        self, outlook_client, caplog, error
    ):
        """認証・通信・取得の失敗は warning を出して error を返し、実行は続ける."""
        outlook_client.get_calendar_events.side_effect = error

        result = _call(tool_call("get_today_events"))

        assert result == EVENTS_ERROR
        (message,) = _warnings(caplog)
        assert str(error) in message


class TestResponsePolicy:
    """応答の方針（サービスがキャラクター設定の後ろに付ける、コード側の指示）.

    ツールの失敗時の戻り値と組み込みの `load_capability` を前提にした文なので、その契約を確かめる。
    """

    def test_response_policy_with_loadable_skills_names_offered_loader_tool(self):
        """スキルを読み込めるときの方針は、実際にモデルへ渡る読み込みツールの名前で指示する.

        読み込みのツールは PydanticAI の組み込みなので、名前が変わればここで気づける。
        """
        skill = Capability(
            id="good-morning",
            description="朝のあいさつ",
            instructions="天気に触れて挨拶する",
            defer_loading=True,
        )
        llm = _run("結論", capabilities=[skill])

        offered = {tool.name for tool in llm.requests[0].function_tools}
        (loader,) = offered - set(TOOL_DESCRIPTIONS)
        assert loader in response_policy(can_load_skills=True)

    def test_response_policy_without_loadable_skills_has_no_loading_rule(self):
        """読み込めるスキルがない（スキル指定・有効なスキルなし）ときは、読み込む指示を入れない."""
        assert "load_capability" not in response_policy(can_load_skills=False)

    def test_response_policy_with_loadable_skills_only_adds_loading_rule(self):
        """読み込めるときの方針は、読み込めないときの方針に読み込みの 1 行を足したもの."""
        without = response_policy(can_load_skills=False).splitlines()
        with_skills = response_policy(can_load_skills=True).splitlines()

        added = [line for line in with_skills if line not in without]
        assert set(without) <= set(with_skills)
        assert len(added) == 1
        assert "load_capability" in added[0]

    @pytest.mark.parametrize("can_load_skills", [True, False])
    def test_response_policy_names_key_that_failing_tools_return(self, can_load_skills):
        """ツールが失敗時に返す JSON のキー（error）の名前で、触れない情報を指示する."""
        (key,) = _call(tool_call("get_weather"), area_code="")

        assert key in response_policy(can_load_skills=can_load_skills)
