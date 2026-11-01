"""POST /talk/sessions/<id>/messages/ のテスト."""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from pydantic_ai.exceptions import ModelHTTPError, ModelTimeoutError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.llm_agents import TALK_CHAT_AGENT, TALK_TITLE_AGENT
from features.talk.models import ChatMessage, ChatSession, TalkConfig
from integrations.langfuse.models import LangfusePromptRef
from tests.fixtures.llm import ScriptedLLM

User = get_user_model()


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.fixture(autouse=True)
def _reset_throttle_counts():
    """talk_chat スロットルの計数をテスト間で持ち越さない."""
    cache.clear()


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
def prompt_refs(db):
    sys_ref = LangfusePromptRef.objects.create(
        name="msg-system",
        langfuse_prompt_name="msg-system",
        fallback_text="あなたは親切な AI です。",
    )
    user_ref = LangfusePromptRef.objects.create(
        name="msg-user",
        langfuse_prompt_name="msg-user",
        fallback_text="dummy",
    )
    return sys_ref, user_ref


@pytest.fixture
def talk_config(prompt_refs):
    sys_ref, user_ref = prompt_refs
    return TalkConfig.objects.create(
        name="chat-session-test",
        display_name="セッション用",
        tts_enabled=False,
        system_prompt_ref=sys_ref,
        user_prompt_ref=user_ref,
    )


@pytest.fixture
def talk_config_tts(prompt_refs):
    sys_ref, user_ref = prompt_refs
    return TalkConfig.objects.create(
        name="chat-session-tts",
        display_name="セッション用TTS",
        tts_enabled=True,
        tts_format="wav",
        tts_model="model",
        tts_style="Neutral",
        system_prompt_ref=sys_ref,
        user_prompt_ref=user_ref,
    )


@pytest.fixture
def session(user, talk_config):
    return ChatSession.objects.create(user=user, config_name=talk_config.name)


def _url(session_id) -> str:
    return f"/talk/sessions/{session_id}/messages/"


def _mock_service(synth_return: dict, title: str = "テストタイトル"):
    """TalkService の synthesize_chat と generate_session_title を mock."""
    svc = MagicMock()
    svc.synthesize_chat.return_value = synth_return
    svc.generate_session_title.return_value = title
    return svc


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

    @patch("features.talk.views.messages.TalkService")
    def test_send_creates_user_and_assistant_messages(
        self, mock_service_class, auth_client, session
    ):
        mock_service_class.return_value = _mock_service(
            {"message": {"role": "assistant", "content": "返信"}}
        )

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

    @patch("features.talk.views.messages.TalkService")
    def test_send_with_tts_saves_audio_file(
        self, mock_service_class, auth_client, talk_config_tts, user
    ):
        sess = ChatSession.objects.create(user=user, config_name=talk_config_tts.name)
        mock_service_class.return_value = _mock_service(
            {
                "message": {"role": "assistant", "content": "音声付き"},
                "audio_data": b"\x00" * 200,
                "audio_format": "wav",
                "audio_content_type": "audio/wav",
            }
        )

        response = auth_client.post(_url(sess.id), {"content": "hi"}, format="json")

        assert response.status_code == 201
        assistant = sess.messages.get(role="assistant")
        assert assistant.audio_file
        assert assistant.audio_format == "wav"
        assert assistant.audio_size_bytes == 200

    @patch("features.talk.views.messages.TalkService")
    def test_first_response_sets_title(self, mock_service_class, auth_client, session):
        mock_service_class.return_value = _mock_service(
            {"message": {"role": "assistant", "content": "返信"}},
            title="自動タイトル",
        )

        auth_client.post(_url(session.id), {"content": "hi"}, format="json")
        session.refresh_from_db()
        assert session.title == "自動タイトル"

    @patch("features.talk.views.messages.TalkService")
    def test_does_not_overwrite_existing_title(
        self, mock_service_class, auth_client, user, talk_config
    ):
        sess = ChatSession.objects.create(
            user=user, config_name=talk_config.name, title="既存タイトル"
        )
        mock_service_class.return_value = _mock_service(
            {"message": {"role": "assistant", "content": "返信"}},
            title="自動タイトル",
        )

        auth_client.post(_url(sess.id), {"content": "hi"}, format="json")
        sess.refresh_from_db()
        assert sess.title == "既存タイトル"

    @patch("features.talk.views.messages.TalkService")
    def test_title_generation_failure_does_not_break(
        self, mock_service_class, auth_client, session
    ):
        svc = MagicMock()
        svc.synthesize_chat.return_value = {
            "message": {"role": "assistant", "content": "返信"}
        }
        svc.generate_session_title.side_effect = RuntimeError("LLM down")
        mock_service_class.return_value = svc

        response = auth_client.post(_url(session.id), {"content": "hi"}, format="json")
        assert response.status_code == 201
        session.refresh_from_db()
        assert session.title == ""  # 失敗時は空のまま

    @patch("features.talk.views.messages.TalkService")
    def test_max_messages_per_session_returns_400(
        self, mock_service_class, auth_client, session
    ):
        for i in range(50):
            ChatMessage.objects.create(
                session=session,
                sequence=i,
                role="user" if i % 2 == 0 else "assistant",
                content=f"#{i}",
            )
        mock_service_class.return_value = _mock_service(
            {"message": {"role": "assistant", "content": "x"}}
        )

        response = auth_client.post(
            _url(session.id), {"content": "もう一個"}, format="json"
        )
        assert response.status_code == 400
        # 上限超過時は user メッセージも保存しない
        assert session.messages.count() == 50

    @patch("features.talk.views.messages.TalkService")
    def test_synthesis_error_returns_502(
        self, mock_service_class, auth_client, session
    ):
        from integrations.llm.exceptions import LLMClientError

        svc = MagicMock()
        svc.synthesize_chat.side_effect = LLMClientError("upstream")
        mock_service_class.return_value = svc

        response = auth_client.post(_url(session.id), {"content": "hi"}, format="json")
        assert response.status_code == 502
        # LLM エラー時はユーザーメッセージもロールバック
        assert session.messages.count() == 0

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    def test_llm_status_error_returns_502_and_rolls_back(
        self, status_code, talk_llm_settings, auth_client, session
    ):
        """LLM の HTTP エラーは 502 になり、ユーザーメッセージも残らない."""
        llm = ScriptedLLM(ModelHTTPError(status_code, "test-alias"))

        with TALK_CHAT_AGENT.override(model=llm.model):
            response = auth_client.post(
                _url(session.id), {"content": "hi"}, format="json"
            )

        assert response.status_code == 502
        assert session.messages.count() == 0

    def test_llm_timeout_returns_504_and_rolls_back(
        self, talk_llm_settings, auth_client, session
    ):
        """LLM のタイムアウトは 504 になり、ユーザーメッセージも残らない."""
        llm = ScriptedLLM(ModelTimeoutError("test-alias", "timeout"))

        with TALK_CHAT_AGENT.override(model=llm.model):
            response = auth_client.post(
                _url(session.id), {"content": "hi"}, format="json"
            )

        assert response.status_code == 504
        assert session.messages.count() == 0

    def test_send_through_real_agents_saves_reply_and_title(
        self, talk_llm_settings, auth_client, session
    ):
        """モデル以外を差し替えずに通し、応答とタイトルが保存される.

        LLM 呼び出しはビューの transaction.atomic の中で走る。
        """
        chat = ScriptedLLM("返信本文")
        title = ScriptedLLM("生成タイトル")

        with (
            TALK_CHAT_AGENT.override(model=chat.model),
            TALK_TITLE_AGENT.override(model=title.model),
        ):
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
        assert chat.requests[0].instructions == "あなたは親切な AI です。"
        assert chat.requests[0].conversation == [("user", "おはよう")]

    def test_session_config_missing_returns_404(self, auth_client, user):
        # 存在しない config を指す session
        sess = ChatSession.objects.create(user=user, config_name="nope")
        response = auth_client.post(_url(sess.id), {"content": "hi"}, format="json")
        assert response.status_code == 404

    @patch(
        "rest_framework.throttling.ScopedRateThrottle.THROTTLE_RATES",
        {"talk_chat": "1/minute"},
    )
    @patch("features.talk.views.messages.TalkService")
    def test_messages_endpoint_rate_limited(
        self, mock_service_class, auth_client, session
    ):
        mock_service_class.return_value = _mock_service(
            {"message": {"role": "assistant", "content": "ok"}}
        )

        first = auth_client.post(_url(session.id), {"content": "1"}, format="json")
        assert first.status_code == 201
        second = auth_client.post(_url(session.id), {"content": "2"}, format="json")
        assert second.status_code == 429
