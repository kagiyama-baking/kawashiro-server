"""チャットのターンのテスト: `Accept` によるモードの切替と事前検証.

事前検証の失敗は SSE を要求しても通常の HTTP ステータスで返す。
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from drf_spectacular.generators import SchemaGenerator
from pydantic_ai.exceptions import ModelTimeoutError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.chat_turn import ChatTurnRunner
from features.talk.models import ChatMessage, ChatSession, TalkConfig
from features.talk.services import TalkService
from features.talk.views._common import SESSION_MAX_MESSAGES
from integrations.langfuse.models import LangfusePromptRef
from integrations.tts.exceptions import TTSTimeoutError
from tests.fixtures.sse import (
    SSE_ACCEPT,
    SSEReader,
    edit_sse,
    event_names,
    send_sse,
    send_url,
)

pytestmark = pytest.mark.usefixtures("chat_turn_env")

User = get_user_model()


@pytest.mark.django_db
class TestPreValidationStaysHttp:
    """事前検証の失敗は SSE を要求しても通常の HTTP ステータスで返す."""

    def _post(self, client, session_id, content="hi"):
        return client.post(
            send_url(session_id),
            {"content": content},
            format="json",
            HTTP_ACCEPT=SSE_ACCEPT,
        )

    def test_unauthenticated_returns_401(self, session):
        response = self._post(APIClient(), session.id)

        assert response.status_code == 401
        assert not response.streaming

    def test_other_users_session_returns_404(self, session):
        other = User.objects.create_user(email="other@example.com", password="x1234567")
        token, _ = Token.objects.get_or_create(user=other)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self._post(client, session.id)

        assert response.status_code == 404
        assert not response.streaming

    def test_invalid_content_returns_400(self, auth_client, session):
        response = self._post(auth_client, session.id, content="")

        assert response.status_code == 400
        assert not response.streaming

    def test_missing_config_returns_404(self, auth_client, user):
        orphan = ChatSession.objects.create(user=user, config_name="nope")

        response = self._post(auth_client, orphan.id)

        assert response.status_code == 404
        assert not response.streaming
        assert "error" in response.data

    def test_message_limit_returns_400(self, chat_llm, auth_client, session):
        ChatMessage.objects.bulk_create(
            ChatMessage(
                session=session,
                sequence=sequence,
                role="user" if sequence % 2 == 0 else "assistant",
                content=f"#{sequence}",
            )
            for sequence in range(SESSION_MAX_MESSAGES)
        )

        response = self._post(auth_client, session.id)

        assert response.status_code == 400
        assert not response.streaming
        assert str(SESSION_MAX_MESSAGES) in response.data["error"]
        assert session.messages.count() == SESSION_MAX_MESSAGES
        assert chat_llm.requests == []

    def test_edit_has_no_message_limit(self, chat_llm, auth_client, session):
        """編集には上限がない（対象より前の履歴だけで上限に達していても編集できる）."""
        messages = [
            ChatMessage.objects.create(
                session=session,
                sequence=sequence,
                role="user" if sequence % 2 == 0 else "assistant",
                content=f"#{sequence}",
            )
            for sequence in range(SESSION_MAX_MESSAGES + 2)
        ]
        chat_llm.enqueue("再生成")
        session.title = "既存"
        session.save()

        events = edit_sse(
            auth_client, session.id, messages[SESSION_MAX_MESSAGES].id
        ).read_all()

        assert event_names(events)[-1] == "done"
        assert session.messages.count() == SESSION_MAX_MESSAGES + 2

    def test_missing_placeholder_config_returns_400(self, auth_client, user, db):
        system_ref = LangfusePromptRef.objects.create(
            name="w-sys", langfuse_prompt_name="w-sys", fallback_text="天気 {{weather}}"
        )
        user_ref = LangfusePromptRef.objects.create(
            name="w-usr", langfuse_prompt_name="w-usr", fallback_text="u"
        )
        config = TalkConfig.objects.create(
            name="no-area",
            display_name="no-area",
            system_prompt_ref=system_ref,
            user_prompt_ref=user_ref,
        )
        target = ChatSession.objects.create(user=user, config_name=config.name)

        response = self._post(auth_client, target.id)

        assert response.status_code == 400
        assert not response.streaming
        assert target.messages.count() == 0

    def test_placeholder_fetch_failure_returns_mapped_status(
        self, talk_llm_settings, auth_client, session
    ):
        """プレースホルダーの取得失敗は handle_synthesis_error と同じ写像になる."""
        with patch.object(
            TalkService,
            "prepare_chat_prompt",
            side_effect=TTSTimeoutError("slow"),
        ):
            response = self._post(auth_client, session.id)

        assert response.status_code == 504
        assert not response.streaming

    def test_missing_llm_settings_returns_500(self, auth_client, session):
        """LLM 設定がなければストリームを始めない."""
        response = self._post(auth_client, session.id)

        assert response.status_code == 500
        assert not response.streaming
        assert response.data == {"error": "チャット応答の生成中に問題が発生しました"}

    @patch(
        "rest_framework.throttling.ScopedRateThrottle.THROTTLE_RATES",
        {"talk_chat": "1/minute"},
    )
    def test_throttled_returns_429(self, chat_llm, title_llm, auth_client, session):
        chat_llm.enqueue("返信")
        send_sse(auth_client, session.id).read_all()

        response = self._post(auth_client, session.id)

        assert response.status_code == 429
        assert not response.streaming


@pytest.mark.django_db
class TestModeSwitch:
    """`Accept` によるモードの切替と SSE のヘッダ."""

    @pytest.mark.parametrize(
        "accept",
        [
            "text/event-stream, application/json",
            "application/json, text/event-stream",
            "text/event-stream;q=0.9, application/json;q=0.8",
            "Text/Event-Stream, application/json",
            "text/event-stream, */*",
        ],
    )
    def test_accept_with_event_stream_returns_sse(
        self, accept, chat_llm, title_llm, auth_client, session
    ):
        chat_llm.enqueue("返信")

        response = auth_client.post(
            send_url(session.id),
            {"content": "hi"},
            format="json",
            HTTP_ACCEPT=accept,
        )

        assert response.status_code == 200
        assert response.streaming
        assert event_names(SSEReader(response).read_all())[-1] == "done"

    @pytest.mark.parametrize(
        "extra",
        [{}, {"HTTP_ACCEPT": "application/json"}, {"HTTP_ACCEPT": "*/*"}],
    )
    def test_accept_without_event_stream_returns_json(
        self, extra, chat_llm, title_llm, auth_client, session
    ):
        chat_llm.enqueue("返信")

        response = auth_client.post(
            send_url(session.id), {"content": "hi"}, format="json", **extra
        )

        assert response.status_code == 201
        assert not response.streaming
        assert response.data["id"] == str(session.id)
        assert len(response.data["messages"]) == 2

    def test_accept_event_stream_only_returns_406(self, chat_llm, auth_client, session):
        """JSONRenderer のみの DRF は text/event-stream 単独を受け付けない.

        クライアントは `Accept: text/event-stream, application/json` を送る前提とする。
        """
        response = auth_client.post(
            send_url(session.id),
            {"content": "hi"},
            format="json",
            HTTP_ACCEPT="text/event-stream",
        )

        assert response.status_code == 406
        assert chat_llm.requests == []

    def test_sse_response_headers(self, chat_llm, title_llm, auth_client, session):
        """プロキシにバッファさせず、変換もキャッシュもさせない."""
        chat_llm.enqueue("返信")

        response = auth_client.post(
            send_url(session.id),
            {"content": "hi"},
            format="json",
            HTTP_ACCEPT=SSE_ACCEPT,
        )

        assert response.headers["Content-Type"] == "text/event-stream; charset=utf-8"
        assert response.headers["Cache-Control"] == "no-cache, no-transform"
        assert response.headers["X-Accel-Buffering"] == "no"
        assert "Connection" not in response.headers
        assert "Content-Length" not in response.headers
        response.close()

    def test_non_ascii_is_sent_as_utf8(self, chat_llm, title_llm, auth_client, session):
        """日本語はエスケープせず UTF-8 のまま流す."""
        chat_llm.enqueue("こんにちは")

        response = auth_client.post(
            send_url(session.id),
            {"content": "hi"},
            format="json",
            HTTP_ACCEPT=SSE_ACCEPT,
        )

        assert "こんにちは".encode() in b"".join(response.streaming_content)

    def test_start_event_is_sent_before_llm_runs(
        self, chat_llm, title_llm, auth_client, session
    ):
        """最初のイベントは LLM の前に流れ、ヘッダが即座に届く."""
        chat_llm.enqueue("返信")
        reader = send_sse(auth_client, session.id)

        assert reader.next_event() == ("start", {})
        assert chat_llm.requests == []
        reader.read_all()

    def test_json_mode_error_event_becomes_http_status(
        self, chat_llm, auth_client, session
    ):
        """JSON モードでは error イベントがそのステータスの応答になる."""
        chat_llm.enqueue(ModelTimeoutError("test-alias", "timeout"))

        response = auth_client.post(
            send_url(session.id), {"content": "hi"}, format="json"
        )

        assert response.status_code == 504
        assert response.data == {
            "error": "サービスへのリクエストがタイムアウトしました"
        }

    def test_json_mode_session_deleted_during_llm_returns_404(
        self, auth_client, session
    ):
        """JSON モードで最後にセッションが消えていたら 404 を返す."""

        def events(self):
            ChatSession.objects.filter(id=session.id).delete()
            yield "done", {}

        with (
            patch.object(TalkService, "prepare_chat_prompt", return_value="s"),
            patch.object(ChatTurnRunner, "events", events),
        ):
            response = auth_client.post(
                send_url(session.id), {"content": "hi"}, format="json"
            )

        assert response.status_code == 404


@pytest.mark.django_db
class TestOpenApiSchema:
    """OpenAPI スキーマのテスト."""

    def test_turn_endpoints_document_event_stream(self):
        """送信と編集のスキーマに text/event-stream が載る."""
        schema = SchemaGenerator().get_schema(request=None, public=True)

        send = schema["paths"]["/talk/sessions/{session_id}/messages/"]["post"]
        edit = schema["paths"]["/talk/sessions/{session_id}/messages/{msg_id}/"][
            "patch"
        ]
        assert set(send["responses"]["200"]["content"]) == {"text/event-stream"}
        assert set(send["responses"]["201"]["content"]) == {"application/json"}
        assert set(edit["responses"]["200"]["content"]) == {
            "application/json",
            "text/event-stream",
        }
        assert "event" in send["responses"]["200"]["description"]
