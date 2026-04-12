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
        """必須フィールドで設定を作成できる."""
        sys_ref, user_ref = prompt_refs
        config = TalkConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            system_prompt_ref=sys_ref,
            user_prompt_ref=user_ref,
        )

        assert config.id is not None
        assert config.name == "morning"
        assert config.display_name == "朝のあいさつ"
        assert config.system_prompt_ref_id == sys_ref.id
        assert config.user_prompt_ref_id == user_ref.id

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

    def test_multiple_configs_allowed(self, prompt_refs):
        """複数の設定を作成できる."""
        TalkConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            **_base_kwargs(prompt_refs),
        )
        TalkConfig.objects.create(
            name="evening",
            display_name="夜のあいさつ",
            **_base_kwargs(prompt_refs),
        )

        assert TalkConfig.objects.count() == 2

    def test_placeholder_defaults(self, prompt_refs):
        """プレースホルダー設定のデフォルト値が正しい."""
        config = TalkConfig.objects.create(
            name="test",
            display_name="テスト",
            **_base_kwargs(prompt_refs),
        )

        assert config.use_weather is False
        assert config.use_events is False
        assert config.use_datetime is True

    def test_create_config_with_all_placeholders(self, prompt_refs):
        """全プレースホルダーを有効にした設定を作成できる."""
        config = TalkConfig.objects.create(
            name="full",
            display_name="フル設定",
            use_weather=True,
            use_events=True,
            use_datetime=True,
            area_code="130010",
            **_base_kwargs(prompt_refs),
        )

        assert config.use_weather is True
        assert config.use_events is True
        assert config.use_datetime is True

    # area_code バリデーション

    def test_area_code_required_when_use_weather_true(self, prompt_refs):
        """use_weather=True の場合、area_code は必須."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="",
            **_base_kwargs(prompt_refs),
        )

        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    def test_area_code_not_required_when_use_weather_false(self, prompt_refs):
        """use_weather=False の場合、area_code は不要."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=False,
            area_code="",
            **_base_kwargs(prompt_refs),
        )
        config.full_clean()

    def test_area_code_valid_6_digits(self, prompt_refs):
        """area_code: 6桁の数字は有効."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="130010",
            **_base_kwargs(prompt_refs),
        )
        config.full_clean()

    def test_area_code_invalid_non_numeric(self, prompt_refs):
        """area_code: 数字以外を含む場合はエラー."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="13001a",
            **_base_kwargs(prompt_refs),
        )
        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    def test_area_code_invalid_too_short(self, prompt_refs):
        """area_code: 6桁未満はエラー."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="12345",
            **_base_kwargs(prompt_refs),
        )
        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    # TTS設定

    def test_tts_enabled_default_is_false(self, prompt_refs):
        """tts_enabled のデフォルト値は False."""
        config = TalkConfig.objects.create(
            name="test",
            display_name="テスト",
            **_base_kwargs(prompt_refs),
        )
        assert config.tts_enabled is False

    def test_tts_options_default_values(self, prompt_refs):
        """TTS オプションのデフォルト値が正しい."""
        config = TalkConfig.objects.create(
            name="test",
            display_name="テスト",
            **_base_kwargs(prompt_refs),
        )

        assert config.tts_model == ""
        assert config.tts_style == "Neutral"
        assert config.tts_style_weight == 1.0
        assert config.tts_speed == 1.0
        assert config.tts_sdp_ratio == 0.2
        assert config.tts_noise_scale == 0.6
        assert config.tts_noise_scale_w == 0.8

    def test_create_config_with_tts_enabled(self, prompt_refs):
        """音声合成を有効にした設定を作成できる."""
        config = TalkConfig.objects.create(
            name="test",
            display_name="テスト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_style_weight=1.5,
            tts_speed=1.2,
            **_base_kwargs(prompt_refs),
        )

        assert config.tts_enabled is True
        assert config.tts_model == "test_model"
        assert config.tts_style == "Happy"

    # get_tts_options() メソッド

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
        """get_tts_options(): TTS有効時は設定を辞書で返す."""
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

    def test_get_tts_options_includes_format(self, prompt_refs):
        """get_tts_options(): format フィールドが含まれる."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            tts_enabled=True,
            tts_format="ogg",
            **_base_kwargs(prompt_refs),
        )
        options = config.get_tts_options()
        assert options["format"] == "ogg"

    def test_tts_format_default_is_wav(self, prompt_refs):
        """tts_format のデフォルト値は wav."""
        config = TalkConfig.objects.create(
            name="test_format",
            display_name="テスト",
            **_base_kwargs(prompt_refs),
        )
        assert config.tts_format == "wav"

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

    # __str__ と verbose_name

    def test_str_returns_display_name(self, prompt_refs):
        """__str__ は display_name を返す."""
        config = TalkConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            **_base_kwargs(prompt_refs),
        )
        assert str(config) == "朝のあいさつ"

    def test_verbose_name(self):
        """verbose_name が正しく設定されている."""
        assert TalkConfig._meta.verbose_name == "会話生成設定"
        assert TalkConfig._meta.verbose_name_plural == "会話生成設定"

    # save() でのバリデーション

    def test_save_validates_area_code_when_use_weather(self, prompt_refs):
        """save(): use_weather=True で不正な area_code でエラー."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="invalid",
            **_base_kwargs(prompt_refs),
        )
        with pytest.raises(ValidationError) as exc_info:
            config.save()
        assert "area_code" in exc_info.value.message_dict

    def test_save_validates_area_code_required_when_use_weather(self, prompt_refs):
        """save(): use_weather=True で area_code 未設定だとエラー."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="",
            **_base_kwargs(prompt_refs),
        )
        with pytest.raises(ValidationError) as exc_info:
            config.save()
        assert "area_code" in exc_info.value.message_dict

    # get_enabled_placeholders() メソッド

    def test_get_enabled_placeholders_all_disabled(self, prompt_refs):
        """get_enabled_placeholders(): 全て無効."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=False,
            use_events=False,
            use_datetime=False,
            **_base_kwargs(prompt_refs),
        )
        assert config.get_enabled_placeholders() == []

    def test_get_enabled_placeholders_all_enabled(self, prompt_refs):
        """get_enabled_placeholders(): 全て有効."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            use_events=True,
            use_datetime=True,
            area_code="130010",
            **_base_kwargs(prompt_refs),
        )
        placeholders = config.get_enabled_placeholders()
        assert placeholders == ["weather", "events", "datetime"]

    def test_get_enabled_placeholders_partial(self, prompt_refs):
        """get_enabled_placeholders(): 一部有効."""
        config = TalkConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            use_events=False,
            use_datetime=True,
            area_code="130010",
            **_base_kwargs(prompt_refs),
        )
        placeholders = config.get_enabled_placeholders()
        assert "weather" in placeholders
        assert "events" not in placeholders
        assert "datetime" in placeholders
