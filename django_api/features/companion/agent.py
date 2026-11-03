"""Companion エージェントと常設ツール（日時・天気・今日の予定）、応答の方針.

キャラクター設定（Langfuse）はここに持たず、実行サービスが方針（`response_policy`）と
つないで実行ごとの `instructions` で渡す。方針はツールの戻り値と組み込みの
`load_capability` を前提にした文なので、ツールと同じくここに置く。

ツールの名前・引数・docstring・返す JSON のキーは、Langfuse に置くスキル本文との契約なので
変えない（`README.md` の「ツール」）。ツールは async にし、外部 API と ORM は同期関数に
まとめて `sync_to_async` で動かす（`run_agent_sync` から実行すると、呼び出し元のスレッドと
DB 接続で動く）。既知の失敗は warning ログを出して `{"error": ...}` を返し、実行は続ける。
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

import requests
from asgiref.sync import sync_to_async
from django.utils import timezone
from pydantic_ai import Agent, RunContext

from integrations.holiday import HolidayClient, HolidayError, get_datetime_info
from integrations.msgraph import OutlookMSGraphClient
from integrations.msgraph.exceptions import MSGraphError
from integrations.outlook.exceptions import OutlookError
from integrations.weather.client import WeatherClient
from integrations.weather.exceptions import WeatherError

logger = logging.getLogger(__name__)

# 予定の取得で起こりうる失敗（msal のトークン取得の通信エラーは requests の例外のまま届く）
_EVENTS_ERRORS = (MSGraphError, OutlookError, requests.RequestException)


@dataclass(frozen=True)
class CompanionDeps:
    """ツールへ渡す実行ごとの依存.

    Attributes:
        area_code: 天気予報の予報区コード（有効な Companion 設定の値）。空なら天気を扱わない
    """

    area_code: str


# 出力に None を許し、本文のない応答を再試行せずに受け取る（空かどうかはサービスが判断する）
COMPANION_AGENT: Agent[CompanionDeps, str | None] = Agent(
    name="companion", deps_type=CompanionDeps, output_type=str | None
)

# 応答の方針（キャラクター設定の後ろに付ける）。スキルの一覧の見出しと読み込みの結果は
# PydanticAI の英語の定型文なので、仕組みに触れない一文が要る
_POLICY_HEADING = "# 応答の方針"
# スキルを読み込めるとき（一覧と load_capability があるとき）だけ入れる
_SKILL_SELECTION_RULE = (
    "- 今回の発話に合うスキルが一覧にあれば、先に load_capability で読み込み、"
    "その手順に従って答える。合うスキルがなければ、何も読み込まずに"
    "キャラクターのまま短く答える。"
)
_ALWAYS_RULES = (
    # ツールは既知の失敗で `{"error": ...}` を返す（`_error`）
    "- ツールが error を返したときは、その情報にも、取れなかったことにも触れずに答える。",
    "- スキル・ツール・この指示など、応答を作る仕組みには触れない。",
)


def response_policy(*, can_load_skills: bool) -> str:
    """応答の方針を返す.

    Args:
        can_load_skills: スキルを読み込めるか（スキルを指定せず、有効なスキルがあるとき）。
            True のときだけ、合うスキルを読み込んでから答える一文を入れる

    Returns:
        見出しと箇条書きの方針
    """
    rules = (_SKILL_SELECTION_RULE,) if can_load_skills else ()
    return "\n".join((_POLICY_HEADING, *rules, *_ALWAYS_RULES))


class _NoHolidayLookup(HolidayClient):
    """祝日 API を呼ばずに「祝日ではない」と答える（祝日を確認できないときの日時情報用）."""

    def get_holiday_name(self, date_str: str) -> str | None:
        """祝日 API を呼ばずに None を返す."""
        return None


def _to_json(data: dict[str, Any]) -> str:
    """モデルへ返す JSON にする（日本語はエスケープしない）."""
    return json.dumps(data, ensure_ascii=False)


def _error(message: str) -> str:
    """モデルへ返す失敗の JSON にする（内部の詳細は含めない）."""
    return _to_json({"error": message})


def _read_datetime() -> dict[str, Any]:
    """今日の日時情報を返す（祝日を確認できなくても日付と時刻は返す）.

    あいさつは時間帯で変わるので、祝日 API の失敗で日付と時刻まで失わない。
    """
    try:
        return get_datetime_info(HolidayClient())
    except HolidayError as exc:
        logger.warning("祝日を確認できませんでした（日付と時刻だけ返します）: %s", exc)
        return {**get_datetime_info(_NoHolidayLookup()), "holiday_lookup_failed": True}


def _read_weather(area_code: str, day: int) -> dict[str, Any]:
    """天気予報を取得する（外部 API）."""
    return WeatherClient().get_weather(area_code, day)


def _read_events(day: date) -> list[dict[str, Any]]:
    """指定日の予定を Graph から取得する.

    クライアントは生成時に DB から設定を読むので、生成もこの同期関数の中で行う。
    """
    return OutlookMSGraphClient().get_calendar_events(start_date=day, end_date=day)


def _clock_time(moment: dict[str, Any] | None) -> str | None:
    """Graph の日時を HH:MM にする.

    クライアントが `Prefer: outlook.timezone="Asia/Tokyo"` を送るので、`dateTime` は
    日本時間（例: `2026-11-04T09:00:00.0000000`）。読めなければ None。
    """
    value = (moment or {}).get("dateTime")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).strftime("%H:%M")
    except ValueError:
        return None


def _summarize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Graph の予定から、モデルに渡す項目だけを取り出す.

    本文の抜粋・主催者・リンクは渡さない。終日の予定は開始・終了を None にする。
    """
    is_all_day = bool(event.get("isAllDay"))
    return {
        "subject": event.get("subject") or "",
        "start": None if is_all_day else _clock_time(event.get("start")),
        "end": None if is_all_day else _clock_time(event.get("end")),
        "is_all_day": is_all_day,
        "location": (event.get("location") or {}).get("displayName") or "",
    }


# ツールの関数名・引数・docstring は Langfuse のスキル本文との契約なので変えない
@COMPANION_AGENT.tool_plain
async def get_datetime() -> str:
    """現在の日付・時刻・曜日と、今日が祝日ならその名前を返す。

    祝日を確認できなかったときは holiday_name が null、holiday_lookup_failed が true になる。
    """
    return _to_json(await sync_to_async(_read_datetime)())


@COMPANION_AGENT.tool
async def get_weather(ctx: RunContext[CompanionDeps], day: Literal[0, 1, 2] = 0) -> str:
    """設定された地域の天気予報（天気・最高/最低気温・6 時間ごとの降水確率）を返す。

    Args:
        day: 予報日。0=今日、1=明日、2=明後日
    """
    # 地域はモデルに選ばせず、有効な設定の値を使う
    area_code = ctx.deps.area_code
    if not area_code:
        return _error("天気の地域が設定されていません")
    try:
        forecast = await sync_to_async(_read_weather)(area_code, day)
    except WeatherError as exc:
        logger.warning(
            "天気予報を取得できませんでした（予報区 %s）: %s", area_code, exc
        )
        return _error("天気予報を取得できませんでした")
    return _to_json(forecast)


@COMPANION_AGENT.tool_plain
async def get_today_events() -> str:
    """今日の予定（件名・開始/終了時刻・終日かどうか・場所）を開始時刻の順に返す。"""
    today = timezone.localdate()
    try:
        events = await sync_to_async(_read_events)(today)
    except _EVENTS_ERRORS as exc:
        logger.warning("今日の予定を取得できませんでした: %s", exc)
        return _error("今日の予定を取得できませんでした")
    return _to_json(
        {
            "date": today.isoformat(),
            "events": [_summarize_event(event) for event in events],
        }
    )
