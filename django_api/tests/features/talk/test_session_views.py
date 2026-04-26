"""ChatSession 関連 API ビューのテスト."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.models import ChatMessage, ChatSession

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="session-view@example.com",
        password="dummypass1234",
        name="Session User",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="other@example.com",
        password="dummypass1234",
        name="Other",
    )


@pytest.fixture
def auth_client(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def other_client(other_user):
    token, _ = Token.objects.get_or_create(user=other_user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.mark.django_db
class TestSessionListCreate:
    URL = "/talk/sessions/"

    def test_list_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get(self.URL)
        assert response.status_code == 401

    def test_list_returns_only_own_sessions(self, auth_client, user, other_user):
        ChatSession.objects.create(user=user, config_name="m", title="自分A")
        ChatSession.objects.create(user=user, config_name="m", title="自分B")
        ChatSession.objects.create(user=other_user, config_name="m", title="他人")

        response = auth_client.get(self.URL)
        assert response.status_code == 200
        # ページネーション形式（results キー）
        assert "results" in response.data
        titles = sorted(item["title"] for item in response.data["results"])
        assert titles == ["自分A", "自分B"]

    def test_list_includes_aggregates(self, auth_client, user):
        session = ChatSession.objects.create(user=user, config_name="m", title="t")
        ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="hi"
        )
        ChatMessage.objects.create(
            session=session,
            sequence=1,
            role="assistant",
            content="hello",
            audio_format="wav",
            audio_size_bytes=12345,
        )

        response = auth_client.get(self.URL)
        item = response.data["results"][0]
        assert item["message_count"] == 2
        assert item["total_audio_bytes"] == 12345

    def test_list_pagination_default_limit_is_20(self, auth_client, user):
        for i in range(25):
            ChatSession.objects.create(user=user, config_name="m", title=f"#{i}")

        response = auth_client.get(self.URL)
        assert response.status_code == 200
        assert response.data["count"] == 25
        assert len(response.data["results"]) == 20

    def test_list_pagination_supports_limit_and_offset(self, auth_client, user):
        for i in range(25):
            ChatSession.objects.create(user=user, config_name="m", title=f"#{i}")

        response = auth_client.get(self.URL + "?limit=5&offset=10")
        assert response.status_code == 200
        assert len(response.data["results"]) == 5

    def test_create_session_with_config_name(self, auth_client, user):
        response = auth_client.post(self.URL, {"config_name": "morning"}, format="json")
        assert response.status_code == 201
        assert response.data["config_name"] == "morning"
        assert response.data["title"] == ""
        assert ChatSession.objects.filter(user=user).count() == 1

    def test_create_requires_config_name(self, auth_client):
        response = auth_client.post(self.URL, {}, format="json")
        assert response.status_code == 400

    def test_create_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.post(self.URL, {"config_name": "m"}, format="json")
        assert response.status_code == 401


@pytest.mark.django_db
class TestSessionDetail:
    def _url(self, session_id) -> str:
        return f"/talk/sessions/{session_id}/"

    def test_get_returns_messages(self, auth_client, user):
        session = ChatSession.objects.create(user=user, config_name="m", title="t")
        ChatMessage.objects.create(
            session=session, sequence=0, role="user", content="a"
        )
        ChatMessage.objects.create(
            session=session, sequence=1, role="assistant", content="b"
        )
        response = auth_client.get(self._url(session.id))
        assert response.status_code == 200
        assert len(response.data["messages"]) == 2
        assert response.data["messages"][0]["content"] == "a"
        assert response.data["message_count"] == 2

    def test_get_other_users_session_returns_404(self, auth_client, other_user):
        session = ChatSession.objects.create(user=other_user, config_name="m")
        response = auth_client.get(self._url(session.id))
        assert response.status_code == 404

    def test_get_nonexistent_returns_404(self, auth_client):
        response = auth_client.get(self._url(uuid.uuid4()))
        assert response.status_code == 404

    def test_patch_updates_title(self, auth_client, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        response = auth_client.patch(
            self._url(session.id), {"title": "新タイトル"}, format="json"
        )
        assert response.status_code == 200
        session.refresh_from_db()
        assert session.title == "新タイトル"

    def test_patch_other_users_session_returns_404(self, auth_client, other_user):
        session = ChatSession.objects.create(user=other_user, config_name="m")
        response = auth_client.patch(
            self._url(session.id), {"title": "x"}, format="json"
        )
        assert response.status_code == 404
        session.refresh_from_db()
        assert session.title == ""

    def test_delete_removes_session(self, auth_client, user):
        session = ChatSession.objects.create(user=user, config_name="m")
        response = auth_client.delete(self._url(session.id))
        assert response.status_code == 204
        assert not ChatSession.objects.filter(id=session.id).exists()

    def test_delete_other_users_session_returns_404(self, auth_client, other_user):
        session = ChatSession.objects.create(user=other_user, config_name="m")
        response = auth_client.delete(self._url(session.id))
        assert response.status_code == 404
        assert ChatSession.objects.filter(id=session.id).exists()
