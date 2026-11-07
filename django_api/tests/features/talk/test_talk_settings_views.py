"""Talk 設定の一覧 API（GET /talk/settings/）のテスト."""

import pytest
from rest_framework.test import APIClient

from tests.fixtures.factories import AgentSkillFactory, TalkSettingFactory

URL = "/talk/settings/"


@pytest.mark.api
@pytest.mark.django_db
class TestTalkSettingsList:
    """有効な Talk 設定と、それぞれで選べる有効なシーン."""

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(URL)

        assert response.status_code == 401

    def test_lists_enabled_settings_and_scenes_in_name_order(self, auth_client):
        """有効な設定だけを名前順に、シーンは有効なものだけを名前順に返す."""
        later = AgentSkillFactory(name="talk-scene-b", description="B の場面")
        earlier = AgentSkillFactory(name="talk-scene-a", description="A の場面")
        disabled = AgentSkillFactory(name="talk-scene-off", is_enabled=False)
        saki = TalkSettingFactory(
            name="さき", skills=[later, earlier, disabled], tts_enabled=True
        )
        hina = TalkSettingFactory(name="ひな")
        TalkSettingFactory(name="無効な設定", is_enabled=False)

        response = auth_client.get(URL)

        assert response.status_code == 200
        assert response.data == {
            "settings": [
                {
                    "id": saki.pk,
                    "name": "さき",
                    "tts_enabled": True,
                    "skills": [
                        {"name": "talk-scene-a", "description": "A の場面"},
                        {"name": "talk-scene-b", "description": "B の場面"},
                    ],
                },
                {"id": hina.pk, "name": "ひな", "tts_enabled": False, "skills": []},
            ]
        }

    def test_without_enabled_settings_returns_empty_list(self, auth_client):
        TalkSettingFactory(name="無効な設定", is_enabled=False)

        response = auth_client.get(URL)

        assert response.data == {"settings": []}

    def test_query_count_does_not_grow_with_settings(
        self, auth_client, django_assert_max_num_queries
    ):
        """設定とシーンは、トークンの確認と合わせて 3 回の問い合わせで返す."""
        for index in range(3):
            TalkSettingFactory(
                name=f"設定{index}",
                skills=[AgentSkillFactory(name=f"talk-scene-{index}")],
            )

        with django_assert_max_num_queries(3):
            response = auth_client.get(URL)

        assert len(response.data["settings"]) == 3
