"""ChatSession 関連 API ビューのテスト."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.models import ChatMessage, ChatSession
from tests.fixtures.factories import AgentSkillFactory, TalkSettingFactory

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
        ChatSession.objects.create(user=user, title="自分A")
        ChatSession.objects.create(user=user, title="自分B")
        ChatSession.objects.create(user=other_user, title="他人")

        response = auth_client.get(self.URL)
        assert response.status_code == 200
        # ページネーション形式（results キー）
        assert "results" in response.data
        titles = sorted(item["title"] for item in response.data["results"])
        assert titles == ["自分A", "自分B"]

    def test_list_includes_aggregates(self, auth_client, user):
        session = ChatSession.objects.create(user=user, title="t")
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

    def test_list_orders_by_updated_at_desc(self, auth_client, user):
        """一覧は updated_at 降順（最新更新が先頭）であること."""
        from django.utils import timezone

        old = ChatSession.objects.create(user=user, title="古い")
        mid = ChatSession.objects.create(user=user, title="中")
        new = ChatSession.objects.create(user=user, title="新しい")

        # 明示的に updated_at を逆順にずらす（auto_now を回避するため update を使用）
        now = timezone.now()
        ChatSession.objects.filter(id=old.id).update(
            updated_at=now - timezone.timedelta(hours=2)
        )
        ChatSession.objects.filter(id=mid.id).update(
            updated_at=now - timezone.timedelta(hours=1)
        )
        ChatSession.objects.filter(id=new.id).update(updated_at=now)

        response = auth_client.get(self.URL)
        titles = [item["title"] for item in response.data["results"]]
        assert titles == ["新しい", "中", "古い"]

    def test_list_pagination_default_limit_is_20(self, auth_client, user):
        for i in range(25):
            ChatSession.objects.create(user=user, title=f"#{i}")

        response = auth_client.get(self.URL)
        assert response.status_code == 200
        assert response.data["count"] == 25
        assert len(response.data["results"]) == 20

    def test_list_pagination_supports_limit_and_offset(self, auth_client, user):
        for i in range(25):
            ChatSession.objects.create(user=user, title=f"#{i}")

        response = auth_client.get(self.URL + "?limit=5&offset=10")
        assert response.status_code == 200
        assert len(response.data["results"]) == 5

    def test_create_session_with_setting_and_scene_returns_detail(
        self, auth_client, user
    ):
        """Talk 設定とシーンを固定したセッションを作り、詳細を返す."""
        scene = AgentSkillFactory(name="talk-scene-cafe", description="カフェで話す")
        setting = TalkSettingFactory(name="ひな", skills=[scene], tts_enabled=True)

        response = auth_client.post(
            self.URL, {"setting": setting.pk, "skill": "talk-scene-cafe"}, format="json"
        )

        assert response.status_code == 201
        assert response.data["setting"] == {"id": setting.pk, "name": "ひな"}
        assert response.data["skill"] == {
            "name": "talk-scene-cafe",
            "description": "カフェで話す",
        }
        assert response.data["tts_enabled"] is True
        assert response.data["title"] == ""
        session = ChatSession.objects.get(pk=response.data["id"])
        assert (session.user, session.setting, session.skill) == (user, setting, scene)

    @pytest.mark.parametrize("body", [{}, {"skill": None}, {"skill": ""}])
    def test_create_session_without_scene(self, auth_client, body):
        """シーンは省略・null・空文字のどれでも「なし」."""
        setting = TalkSettingFactory(name="ひな")

        response = auth_client.post(
            self.URL, {"setting": setting.pk, **body}, format="json"
        )

        assert response.status_code == 201
        assert response.data["skill"] is None
        assert response.data["tts_enabled"] is False
        assert ChatSession.objects.get(pk=response.data["id"]).skill is None

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ({}, "Talk 設定を選んでください"),
            ({"setting": None}, "Talk 設定を選んでください"),
            ({"setting": "abc"}, "Talk 設定は ID で指定してください"),
            ({"setting": 999999}, "選んだ Talk 設定は見つからないか、無効です"),
            ({"config_name": "morning"}, "Talk 設定を選んでください"),
        ],
    )
    def test_create_with_invalid_setting_returns_400(self, auth_client, body, message):
        """Talk 設定がない・ID でない・見つからない（旧プリセット名だけの本文も）は 400."""
        response = auth_client.post(self.URL, body, format="json")

        assert response.status_code == 400
        assert response.data == {"setting": [message]}
        assert ChatSession.objects.count() == 0

    def test_create_with_disabled_setting_returns_400(self, auth_client):
        """無効な Talk 設定ではセッションを作れない."""
        setting = TalkSettingFactory(name="無効", is_enabled=False)

        response = auth_client.post(self.URL, {"setting": setting.pk}, format="json")

        assert response.status_code == 400
        assert response.data == {
            "setting": ["選んだ Talk 設定は見つからないか、無効です"]
        }

    @pytest.mark.parametrize("enabled", [True, False])
    def test_create_with_unknown_or_disabled_scene_returns_400(
        self, auth_client, enabled
    ):
        """登録のない・無効なシーンは 400."""
        scene = AgentSkillFactory(name="talk-scene-off", is_enabled=False)
        setting = TalkSettingFactory(name="ひな", skills=[scene])
        name = "talk-scene-none" if enabled else scene.name

        response = auth_client.post(
            self.URL, {"setting": setting.pk, "skill": name}, format="json"
        )

        assert response.status_code == 400
        assert response.data == {"skill": ["選んだシーンは見つからないか、無効です"]}

    def test_create_with_scene_not_in_setting_returns_400(self, auth_client):
        """Talk 設定で選んでいないシーンは 400."""
        AgentSkillFactory(name="talk-scene-cafe")
        setting = TalkSettingFactory(name="ひな")

        response = auth_client.post(
            self.URL, {"setting": setting.pk, "skill": "talk-scene-cafe"}, format="json"
        )

        assert response.status_code == 400
        assert response.data == {
            "skill": ["このシーンは選んだ Talk 設定では使えません"]
        }

    def test_create_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.post(self.URL, {"setting": 1}, format="json")
        assert response.status_code == 401

    def test_list_items_include_setting_scene_and_voice(self, auth_client, user):
        """一覧の各項目は Talk 設定・シーン・音声の有無を持つ（Talk 設定なしは null と false）."""
        scene = AgentSkillFactory(name="talk-scene-cafe", description="カフェで話す")
        setting = TalkSettingFactory(name="ひな", skills=[scene], tts_enabled=True)
        ChatSession.objects.create(user=user, setting=setting, skill=scene, title="新")
        ChatSession.objects.create(user=user, title="旧")

        response = auth_client.get(self.URL)

        items = {item["title"]: item for item in response.data["results"]}
        assert (items["新"]["setting"], items["新"]["skill"]) == (
            {"id": setting.pk, "name": "ひな"},
            {"name": "talk-scene-cafe", "description": "カフェで話す"},
        )
        assert items["新"]["tts_enabled"] is True
        assert (items["旧"]["setting"], items["旧"]["skill"]) == (None, None)
        assert items["旧"]["tts_enabled"] is False


@pytest.mark.django_db
class TestSessionDetail:
    def _url(self, session_id) -> str:
        return f"/talk/sessions/{session_id}/"

    def test_get_returns_messages(self, auth_client, user):
        session = ChatSession.objects.create(user=user, title="t")
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
        session = ChatSession.objects.create(user=other_user)
        response = auth_client.get(self._url(session.id))
        assert response.status_code == 404

    def test_get_nonexistent_returns_404(self, auth_client):
        response = auth_client.get(self._url(uuid.uuid4()))
        assert response.status_code == 404

    def test_patch_updates_title(self, auth_client, user):
        session = ChatSession.objects.create(user=user)
        response = auth_client.patch(
            self._url(session.id), {"title": "新タイトル"}, format="json"
        )
        assert response.status_code == 200
        session.refresh_from_db()
        assert session.title == "新タイトル"

    def test_patch_other_users_session_returns_404(self, auth_client, other_user):
        session = ChatSession.objects.create(user=other_user)
        response = auth_client.patch(
            self._url(session.id), {"title": "x"}, format="json"
        )
        assert response.status_code == 404
        session.refresh_from_db()
        assert session.title == ""

    def test_delete_removes_session(self, auth_client, user):
        session = ChatSession.objects.create(user=user)
        response = auth_client.delete(self._url(session.id))
        assert response.status_code == 204
        assert not ChatSession.objects.filter(id=session.id).exists()

    def test_delete_other_users_session_returns_404(self, auth_client, other_user):
        session = ChatSession.objects.create(user=other_user)
        response = auth_client.delete(self._url(session.id))
        assert response.status_code == 404
        assert ChatSession.objects.filter(id=session.id).exists()
