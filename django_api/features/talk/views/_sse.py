"""チャットのターンの応答（SSE / JSON の切替）."""

import json
from collections.abc import Iterator
from contextlib import closing
from typing import Any

from django.http import HttpResponseBase, StreamingHttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.utils.encoders import JSONEncoder

# chat_turn は views._common に依存する。views パッケージは読み込み時に全ビューを
# import するので、属性を直接 import すると chat_turn から読み始めたときに循環する。
from .. import chat_turn
from ..models import ChatSession
from ..serializers import ChatSessionDetailSerializer

SSE_MEDIA_TYPE = "text/event-stream"

# gunicorn は最初の書き込みでヘッダを送り、以降の書き込みもそのまま送る。
# プロキシ（nginx）にはバッファも変換もキャッシュもさせない。
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}

SSE_RESPONSE = OpenApiResponse(
    response=OpenApiTypes.STR,
    description=(
        "`Accept` に `text/event-stream` を含むときの応答（SSE）。"
        "`Accept: text/event-stream, application/json` を指定する（単独だと 406）。"
        "各 event は `event: <名前>` と `data: <JSON>` の 2 行で、順に "
        "`start`, `delta{text}`, `message{user, assistant}`, "
        "`audio{message_id, audio_url, audio_format, audio_size_bytes}` または "
        "`audio_error{message_id, error}`, `title{title}`, "
        "`done{title, message_count, total_audio_bytes, updated_at}` が流れる。"
        "LLM の失敗は `error{status, error}` で終わり、何も保存しない。"
        "途中で切断すると、ユーザー発話と届いた分の応答を保存する。"
    ),
)


def format_sse(event: str, data: dict[str, Any]) -> bytes:
    """1 イベントを SSE の形式にする.

    JSON は改行を含まないので、`data:` は常に 1 行になる。
    """
    payload = json.dumps(data, ensure_ascii=False, cls=JSONEncoder)
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _wants_event_stream(request) -> bool:
    return SSE_MEDIA_TYPE in request.headers.get("Accept", "").lower()


def _encode_events(events: "Iterator[chat_turn.TurnEvent]") -> Iterator[bytes]:
    """イベントの列をバイト列にする.

    切断で閉じられたら、内側のジェネレータも閉じて `ChatTurnRunner` に伝える。
    """
    with closing(events):
        for event, data in events:
            yield format_sse(event, data)


def _consume_as_json(
    request,
    plan: "chat_turn.TurnPlan",
    runner: "chat_turn.ChatTurnRunner",
    success_status: int,
) -> Response:
    """イベントの列を最後まで消費して、セッション詳細の JSON を返す.

    `error` イベントはそのステータスの応答にする。音声の失敗は本文に影響しないので無視する。
    """
    failure: dict[str, Any] | None = None
    for event, data in runner.events():
        if event == "error":
            failure = data
    if failure is not None:
        return Response({"error": failure["error"]}, status=failure["status"])

    session = ChatSession.objects.filter(id=plan.session.id).first()
    if session is None:
        return Response(status=status.HTTP_404_NOT_FOUND)
    serializer = ChatSessionDetailSerializer(session, context={"request": request})
    return Response(serializer.data, status=success_status)


def respond_with_turn(
    request, plan: "chat_turn.TurnPlan", success_status: int
) -> HttpResponseBase:
    """ターンを実行する応答を返す.

    `Accept` に `text/event-stream` を含むときだけ SSE にする。それ以外は同じイベント列を
    最後まで消費してから JSON で返す。

    Args:
        request: リクエスト
        plan: `prepare_turn` の結果
        success_status: JSON モードで成功したときの HTTP ステータス

    Returns:
        SSE なら `StreamingHttpResponse`、JSON なら `Response`
    """
    runner = chat_turn.ChatTurnRunner(plan, request=request)
    if not _wants_event_stream(request):
        return _consume_as_json(request, plan, runner, success_status)
    return StreamingHttpResponse(
        _encode_events(runner.events()),
        content_type=f"{SSE_MEDIA_TYPE}; charset=utf-8",
        headers=_SSE_HEADERS,
    )
