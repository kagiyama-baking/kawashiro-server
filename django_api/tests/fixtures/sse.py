"""SSE 応答を読むテスト用ヘルパ."""

import json

SSE_ACCEPT = "text/event-stream, application/json"

# デバウンスの幅より長い間隔（別の delta に分かれる）
SEPARATE_DELTAS = 0.12


def send_url(session_id) -> str:
    return f"/talk/sessions/{session_id}/messages/"


def edit_url(session_id, msg_id) -> str:
    return f"/talk/sessions/{session_id}/messages/{msg_id}/"


def parse_event(chunk: bytes) -> tuple[str, dict]:
    """1 イベント分のバイト列を解釈する（形式も確かめる）."""
    text = chunk.decode("utf-8")
    assert text.endswith("\n\n")
    event_line, data_line = text[:-2].split("\n")
    assert event_line.startswith("event: ")
    assert data_line.startswith("data: ")
    return event_line.removeprefix("event: "), json.loads(
        data_line.removeprefix("data: ")
    )


class SSEReader:
    """SSE の応答を 1 イベントずつ読む."""

    def __init__(self, response):
        assert response.streaming
        self.response = response
        self._chunks = iter(response.streaming_content)

    def next_event(self) -> tuple[str, dict]:
        return parse_event(next(self._chunks))

    def read_until(self, name: str) -> list[tuple[str, dict]]:
        """指定したイベントまで読み、読んだ分を返す."""
        events = []
        while True:
            events.append(self.next_event())
            if events[-1][0] == name:
                return events

    def read_all(self) -> list[tuple[str, dict]]:
        return [parse_event(chunk) for chunk in self._chunks]

    def disconnect(self) -> None:
        """WSGI サーバーが書き込みの失敗で応答を閉じるのと同じことをする."""
        self.response.close()


def send_sse(client, session_id, content: str = "おはよう") -> SSEReader:
    response = client.post(
        send_url(session_id),
        {"content": content},
        format="json",
        HTTP_ACCEPT=SSE_ACCEPT,
    )
    assert response.status_code == 200
    return SSEReader(response)


def edit_sse(client, session_id, msg_id, content: str = "編集後") -> SSEReader:
    response = client.patch(
        edit_url(session_id, msg_id),
        {"content": content},
        format="json",
        HTTP_ACCEPT=SSE_ACCEPT,
    )
    assert response.status_code == 200
    return SSEReader(response)


def event_names(events: list[tuple[str, dict]]) -> list[str]:
    """イベント名の並びを返す（連続する delta は 1 つにまとめる）."""
    names: list[str] = []
    for name, _ in events:
        if not (name == "delta" and names and names[-1] == "delta"):
            names.append(name)
    return names


def event_data(events: list[tuple[str, dict]], name: str) -> dict:
    return next(data for event, data in events if event == name)


def joined_deltas(events: list[tuple[str, dict]]) -> str:
    return "".join(data["text"] for event, data in events if event == "delta")


def saved_messages(session) -> list[tuple[int, str, str]]:
    return [
        (message.sequence, message.role, message.content)
        for message in session.messages.order_by("sequence")
    ]


def audio_files(media_root) -> list:
    return [path for path in media_root.rglob("*") if path.is_file()]
