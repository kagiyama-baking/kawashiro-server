"""TalkConfig モデルのテスト"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from features.talk.models import TalkConfig
from integrations.langfuse.models import LangfusePromptRef


@pytest.fixture
def prompt_refs(db):
    """テスト用の system/user プロンプト参照."""
    sys_ref = LangfusePromptRef.objects.create(
        name="talk-model-test-system",
        langfuse_prompt_name="talk-model-test-system",
        fallback_text="システムプロンプト",
    )
    user_ref = LangfusePromptRef.objects.create(
        name="talk-model-test-user",
        langfuse_prompt_name="talk-model-test-user",
        fallback_text="ユーザープロンプト",
    )
    return sys_ref, user_ref


def _base_kwargs(prompt_refs):
    sys_ref, user_ref = prompt_refs
    return {
        "system_prompt_ref": sys_ref,
        "user_prompt_ref": user_ref,
    }


@pytest.mark.django_db
class TestTalkConfig:
    """TalkConfig モデルのテスト"""

    def test_create_config_with_required_fields(self, prompt_refs):
        """必須フィールドで設定を作成でき、複数件の作成も可能なこと"""
        sys_ref, user_ref = prompt_refs

        config = TalkConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            system_prompt_ref=sys_ref,
            user_prompt_ref=user_ref,
        )
        TalkConfig.objects.create(
            name="evening",
            display_name="夜のあいさつ",
            **_base_kwargs(prompt_refs),
        )

        assert config.id is not None
        assert config.name == "morning"
        assert config.display_name == "朝のあいさつ"
        assert config.system_prompt_ref_id == sys_ref.id
        assert config.user_prompt_ref_id == user_ref.id
        assert TalkConfig.objects.count() == 2

    def test_name_is_unique(self, prompt_refs):
        """name は一意."""
        TalkConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            **_base_kwargs(prompt_refs),
        )
        with pytest.raises((IntegrityError, ValidationError)):
            TalkConfig.objects.create(
                name="morning",
                display_name="別の朝のあいさつ",
                **_base_kwargs(prompt_refs),
            )

    @pytest.mark.parametrize(
        "area_code, expect_error",
        [
            pytest.param("", False, id="empty_is_valid"),
            pytest.param("130010", False, id="six_digits_valid"),
            pytest.param("13001a", True, id="non_numeric"),
            pytest.param("12345", True, id="too_short"),
        ],
    )
    def test_area_code_validation(self, prompt_refs, area_code, expect_error):
        """area_code のバリデーション挙動"""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            area_code=area_code,
            **_base_kwargs(prompt_refs),
        )

        if expect_error:
            with pytest.raises(ValidationError) as exc_info:
                config.full_clean()
            assert "area_code" in exc_info.value.message_dict
        else:
            config.full_clean()

    def test_tts_defaults(self, prompt_refs):
        """TTS 関連フィールドのデフォルト値"""
        config = TalkConfig.objects.create(
            name="test",
            display_name="テスト",
            **_base_kwargs(prompt_refs),
        )

        assert config.tts_enabled is False
        assert config.tts_model == ""
        assert config.tts_style == "Neutral"
        assert config.tts_style_weight == 1.0
        assert config.tts_speed == 1.0
        assert config.tts_sdp_ratio == 0.2
        assert config.tts_noise_scale == 0.6
        assert config.tts_noise_scale_w == 0.8
        assert config.tts_format == "wav"

    def test_get_tts_options_when_disabled(self, prompt_refs):
        """get_tts_options(): TTS無効時は None を返す."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            tts_enabled=False,
            **_base_kwargs(prompt_refs),
        )
        assert config.get_tts_options() is None

    def test_get_tts_options_when_enabled(self, prompt_refs):
        """get_tts_options(): TTS有効時は設定を辞書で返す（format 含む）"""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_style_weight=1.5,
            tts_speed=1.2,
            tts_sdp_ratio=0.3,
            tts_noise_scale=0.5,
            tts_noise_scale_w=0.7,
            **_base_kwargs(prompt_refs),
        )
        options = config.get_tts_options()

        assert options is not None
        assert options["model"] == "test_model"
        assert options["style"] == "Happy"
        assert options["style_weight"] == 1.5
        assert options["speed"] == 1.2
        assert options["sdp_ratio"] == 0.3
        assert options["noise_scale"] == 0.5
        assert options["noise_scale_w"] == 0.7
        assert options["format"] == "wav"

    def test_get_tts_options_with_custom_format(self, prompt_refs):
        """get_tts_options(): tts_format が wav 以外でも反映されること"""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            tts_enabled=True,
            tts_format="ogg",
            **_base_kwargs(prompt_refs),
        )
        options = config.get_tts_options()
        assert options["format"] == "ogg"

    def test_get_tts_options_model_empty_returns_none(self, prompt_refs):
        """get_tts_options(): tts_model が空文字の場合は model が None."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            tts_enabled=True,
            tts_model="",
            **_base_kwargs(prompt_refs),
        )
        options = config.get_tts_options()
        assert options["model"] is None

    def test_str_returns_display_name(self, prompt_refs):
        """__str__ は display_name を返す."""
        config = TalkConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            **_base_kwargs(prompt_refs),
        )
        assert str(config) == "朝のあいさつ"
