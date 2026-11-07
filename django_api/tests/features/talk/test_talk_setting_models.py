"""Talk 設定（TalkSetting）と、チャットセッションの Talk 設定・シーンのテスト."""

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db.models import ProtectedError

from features.talk.models import ChatSession, TalkSetting
from tests.fixtures.factories import (
    AgentSkillFactory,
    PromptFactory,
    TalkSettingFactory,
)

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="talk-setting@example.com",
        password="dummypass1234",
        name="Talk Setting User",
    )


@pytest.mark.integration
@pytest.mark.django_db
class TestTalkSetting:
    """Talk 設定のモデル."""

    def test_talk_setting_defaults_to_enabled_without_scenes_and_voice(self):
        """既定は有効・シーンなし・音声なし."""
        setting = TalkSettingFactory()

        assert setting.is_enabled is True
        assert list(setting.skills.all()) == []
        assert setting.get_tts_options() is None

    def test_multiple_settings_can_be_enabled_at_once(self):
        """複数を有効にできる（1 件を有効にしても、ほかは無効にならない）."""
        first = TalkSettingFactory(name="ひな")
        second = TalkSettingFactory(name="さき")

        first.refresh_from_db()
        second.refresh_from_db()
        assert (first.is_enabled, second.is_enabled) == (True, True)

    def test_talk_setting_with_duplicate_name_raises_validation_error(self):
        """名前は一意（保存時の full_clean で止まる）."""
        existing = TalkSettingFactory(name="ひな")

        with pytest.raises(ValidationError) as exc_info:
            TalkSetting(name="ひな", system_prompt=existing.system_prompt).save()

        assert "name" in exc_info.value.message_dict

    def test_talk_setting_with_blank_name_raises_validation_error(self):
        """名前は必須."""
        with pytest.raises(ValidationError) as exc_info:
            TalkSetting(name="", system_prompt=PromptFactory()).save()

        assert "name" in exc_info.value.message_dict

    def test_settings_are_ordered_by_name_and_shown_by_name(self):
        """名前順に並び、表示は名前."""
        TalkSettingFactory(name="b-setting")
        TalkSettingFactory(name="a-setting")

        assert [str(s) for s in TalkSetting.objects.all()] == [
            "a-setting",
            "b-setting",
        ]

    def test_get_tts_options_when_tts_enabled_returns_voice_options(self):
        """音声を有効にすると、合成の指定を返す（AbstractTTSSettings と同じ）."""
        setting = TalkSettingFactory(
            tts_enabled=True, tts_model="hiroki", tts_format="mp3"
        )

        options = setting.get_tts_options()

        assert options is not None
        assert (options["model"], options["format"]) == ("hiroki", "mp3")

    def test_scene_selected_by_two_settings_is_shared(self):
        """1 つのスキルを 2 つの設定のシーンに選べる（逆参照名は talk_settings）."""
        scene = AgentSkillFactory(name="talk-scene-cafe")
        first = TalkSettingFactory(skills=[scene])
        second = TalkSettingFactory(skills=[scene])

        assert set(scene.talk_settings.all()) == {first, second}

    def test_deleting_scene_selected_only_in_setting_removes_it_from_selection(self):
        """チャットで使っていないスキルは消せ、設定の選択から外れる."""
        scene = AgentSkillFactory(name="talk-scene-cafe")
        setting = TalkSettingFactory(skills=[scene])

        scene.delete()

        assert list(setting.skills.all()) == []

    def test_verbose_name_is_talk_setting(self):
        """admin の表示名は Talk 設定."""
        assert TalkSetting._meta.verbose_name == "Talk 設定"

    def test_talk_app_has_no_preset_model(self):
        """旧会話生成設定（プリセット。TalkConfig）のモデルはない."""
        with pytest.raises(LookupError):
            apps.get_model("talk", "TalkConfig")


@pytest.mark.integration
@pytest.mark.django_db
class TestChatSessionTalkSetting:
    """チャットセッションの Talk 設定とシーン."""

    def test_chat_session_with_setting_has_no_scene(self, user):
        """Talk 設定だけで作れる（シーンなし）."""
        setting = TalkSettingFactory()

        session = ChatSession.objects.create(user=user, setting=setting)

        session.refresh_from_db()
        assert (session.setting, session.skill) == (setting, None)
        assert list(setting.chat_sessions.all()) == [session]

    def test_chat_session_with_scene_keeps_skill(self, user):
        """シーンを選んだセッションはスキルを持つ（逆参照名は talk_chat_sessions）."""
        scene = AgentSkillFactory(name="talk-scene-cafe")
        setting = TalkSettingFactory(skills=[scene])

        session = ChatSession.objects.create(user=user, setting=setting, skill=scene)

        assert list(scene.talk_chat_sessions.all()) == [session]

    def test_deleting_setting_used_by_chat_raises_protected_error(self, user):
        """チャットで使った Talk 設定は消せない（無効にする）."""
        setting = TalkSettingFactory()
        ChatSession.objects.create(user=user, setting=setting)

        with pytest.raises(ProtectedError):
            setting.delete()

    def test_deleting_scene_used_by_chat_raises_protected_error(self, user):
        """チャットで使ったスキルは消せない（無効にする）."""
        scene = AgentSkillFactory(name="talk-scene-cafe")
        setting = TalkSettingFactory(skills=[scene])
        ChatSession.objects.create(user=user, setting=setting, skill=scene)

        with pytest.raises(ProtectedError):
            scene.delete()

    def test_chat_session_has_no_preset_name_field(self):
        """チャットは旧プリセット名（config_name）を持たない."""
        with pytest.raises(FieldDoesNotExist):
            ChatSession._meta.get_field("config_name")
