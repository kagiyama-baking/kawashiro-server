"""POST /talk/sessions/<id>/messages/ のテスト（JSON モード）.

`Accept` に `text/event-stream` を含まないときの応答を確かめる。SSE モードは
`test_chat_turn_sse.py`、LLM はモデルだけを差し替えて実行する。
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from pydantic_ai.exceptions import ModelHTTPError, ModelTimeoutError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.models import ChatMessage, ChatSession, TalkSetting
from features.talk.services import TalkService
from integrations.llm.models import Prompt
from integrations.tts.client import TTSResult
from integrations.tts.exceptions import TTSNetworkError

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="msg-view@example.com",
        password="dummypass1234",
        name="Msg User",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="msg-other@example.com",
        password="dummypass1234",
    )


def _client_for(u):
    token, _ = Token.objects.get_or_create(user=u)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return c


@pytest.fixture
def auth_client(user):
    return _client_for(user)


@pytest.fixture
def system_prompt(db, langfuse_prompts):
    """Talk 設定のシステムプロンプトの参照（本文は Langfuse の代役の production にある）."""
    langfuse_prompts[("msg-system", "production")] = "あなたは親切な AI です。"
    return Prompt.objects.create(name="msg-system")


@pytest.fixture
def talk_setting(system_prompt):
    return TalkSetting.objects.create(name="セッション用", system_prompt=system_prompt)


@pytest.fixture
def tts_setting(system_prompt):
    return TalkSetting.objects.create(
        name="セッション用TTS",
        tts_enabled=True,
        tts_format="wav",
        tts_model="model",
        tts_style="Neutral",
        system_prompt=system_prompt,
    )


@pytest.fixture
def session(user, talk_setting):
    return ChatSession.objects.create(user=user, setting=talk_setting)


def _url(session_id) -> str:
    return f"/talk/sessions/{session_id}/messages/"


@pytest.mark.django_db
class TestSessionMessagePost:
    def test_unauthenticated_returns_401(self, session):
        response = APIClient().post(_url(session.id), {"content": "hi"}, format="json")
        assert response.status_code == 401

    def test_other_users_session_returns_404(self, session, other_user):
        client = _client_for(other_user)
        response = client.post(_url(session.id), {"content": "hi"}, format="json")
        assert response.status_code == 404

    def test_empty_content_returns_400(self, auth_client, session):
        response = auth_client.post(_url(session.id), {"content": ""}, format="json")
        assert response.status_code == 400

    def test_content_over_limit_returns_400(self, auth_client, session):
        response = auth_client.post(
            _url(session.id), {"content": "あ" * 4001}, format="json"
        )
        assert response.status_code == 400

    def test_send_creates_user_and_assistant_messages(
        self, chat_llm, title_llm, auth_client, session
    ):
        chat_llm.enqueue("返信")

        response = auth_client.post(
            _url(session.id), {"content": "おはよう"}, format="json"
        )

        assert response.status_code == 201
        msgs = list(session.messages.order_by("sequence"))
        assert len(msgs) == 2
        assert msgs[0].role == "user" and msgs[0].content == "おはよう"
        assert msgs[1].role == "assistant" and msgs[1].content == "返信"
        # レスポンスは session 詳細
        assert response.data["id"] == str(session.id)
        assert len(response.data["messages"]) == 2

    @patch("features.talk.services.TTSClient")
    def test_send_with_tts_saves_audio_file(
        self, mock_tts_class, chat_llm, title_llm, auth_client, tts_setting, user
    ):
        sess = ChatSession.objects.create(user=user, setting=tts_setting)
        chat_llm.enqueue("音声付き")
        mock_tts_class.return_value.synthesize.return_value = TTSResult(
            audio_data=b"\x00" * 200, content_type="audio/wav", format="wav"
        )

        response = auth_client.post(_url(sess.id), {"content": "hi"}, format="json")

        assert response.status_code == 201
        assistant = sess.messages.get(role="assistant")
        assert assistant.audio_file
        assert assistant.audio_format == "wav"
        assert assistant.audio_size_bytes == 200
        assert response.data["total_audio_bytes"] == 200
        assert response.data["messages"][1]["audio_url"].endswith(
            f"/talk/sessions/{sess.id}/audio/{assistant.id}/"
        )

    @patch("features.talk.services.TTSClient")
    def test_tts_failure_returns_201_and_keeps_reply(
        self, mock_tts_class, chat_llm, title_llm, auth_client, tts_setting, user
    ):
        """音声合成の失敗は致命にせず、本文を残して 201 を返す（以前は 502）."""
        sess = ChatSession.objects.create(user=user, setting=tts_setting)
        chat_llm.enqueue("本文")
        mock_tts_class.return_value.synthesize.side_effect = TTSNetworkError("down")

        response = auth_client.post(_url(sess.id), {"content": "hi"}, format="json")

        assert response.status_code == 201
        assert [m["content"] for m in response.data["messages"]] == ["hi", "本文"]
        assistant = sess.messages.get(role="assistant")
        assert not assistant.audio_file
        assert response.data["messages"][1]["audio_url"] is None

    def test_first_response_sets_title(self, chat_llm, title_llm, auth_client, session):
        chat_llm.enqueue("返信")
        title_llm.enqueue("自動タイトル")

        response = auth_client.post(_url(session.id), {"content": "hi"}, format="json")

        session.refresh_from_db()
        assert session.title == "自動タイトル"
        assert response.data["title"] == "自動タイトル"

    def test_does_not_overwrite_existing_title(
        self, chat_llm, title_llm, auth_client, user, talk_setting
    ):
        sess = ChatSession.objects.create(
            user=user, setting=talk_setting, title="既存タイトル"
        )
        chat_llm.enqueue("返信")

        auth_client.post(_url(sess.id), {"content": "hi"}, format="json")

        sess.refresh_from_db()
        assert sess.title == "既存タイトル"
        assert title_llm.requests == []

    def test_title_generation_failure_does_not_break(
        self, chat_llm, auth_client, session
    ):
        chat_llm.enqueue("返信")

        with patch.object(
            TalkService, "generate_session_title", side_effect=RuntimeError("LLM down")
        ):
            response = auth_client.post(
                _url(session.id), {"content": "hi"}, format="json"
            )

        assert response.status_code == 201
        session.refresh_from_db()
        assert session.title == ""  # 失敗時は空のまま

    def test_max_messages_per_session_returns_400(self, auth_client, session, chat_llm):
        for i in range(50):
            ChatMessage.objects.create(
                session=session,
                sequence=i,
                role="user" if i % 2 == 0 else "assistant",
                content=f"#{i}",
            )

        response = auth_client.post(
            _url(session.id), {"content": "もう一個"}, format="json"
        )
        assert response.status_code == 400
        # 上限超過時は user メッセージも保存しない
        assert session.messages.count() == 50
        assert chat_llm.requests == []

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    def test_llm_status_error_returns_502_and_saves_nothing(
        self, status_code, chat_llm, auth_client, session
    ):
        """LLM の HTTP エラーは 502 になり、ユーザーメッセージも残らない."""
        chat_llm.enqueue(ModelHTTPError(status_code, "test-alias"))

        response = auth_client.post(_url(session.id), {"content": "hi"}, format="json")

        assert response.status_code == 502
        assert session.messages.count() == 0

    def test_llm_timeout_returns_504_and_saves_nothing(
        self, chat_llm, auth_client, session
    ):
        """LLM のタイムアウトは 504 になり、ユーザーメッセージも残らない."""
        chat_llm.enqueue(ModelTimeoutError("test-alias", "timeout"))

        response = auth_client.post(_url(session.id), {"content": "hi"}, format="json")

        assert response.status_code == 504
        assert session.messages.count() == 0

    def test_send_through_real_agents_saves_reply_and_title(
        self, chat_llm, title_llm, auth_client, session
    ):
        """モデル以外を差し替えずに通し、応答とタイトルが保存される."""
        chat_llm.enqueue("返信本文")
        title_llm.enqueue("生成タイトル")

        response = auth_client.post(
            _url(session.id), {"content": "おはよう"}, format="json"
        )

        assert response.status_code == 201
        msgs = list(session.messages.order_by("sequence"))
        assert [(m.role, m.content) for m in msgs] == [
            ("user", "おはよう"),
            ("assistant", "返信本文"),
        ]
        session.refresh_from_db()
        assert session.title == "生成タイトル"
        assert chat_llm.requests[0].instructions == "あなたは親切な AI です。"
        assert chat_llm.requests[0].conversation == [("user", "おはよう")]

    def test_session_without_setting_returns_400(self, auth_client, user):
        """Talk 設定のない（移行できなかった旧プリセットの）チャットは続けられない."""
        sess = ChatSession.objects.create(user=user)
        response = auth_client.post(_url(sess.id), {"content": "hi"}, format="json")
        assert response.status_code == 400
        assert "Talk 設定がない" in response.data["error"]

    @patch(
        "rest_framework.throttling.ScopedRateThrottle.THROTTLE_RATES",
        {"talk_chat": "1/minute"},
    )
    def test_messages_endpoint_rate_limited(
        self, chat_llm, title_llm, auth_client, session
    ):
        chat_llm.enqueue("ok")

        first = auth_client.post(_url(session.id), {"content": "1"}, format="json")
        assert first.status_code == 201
        second = auth_client.post(_url(session.id), {"content": "2"}, format="json")
        assert second.status_code == 429
