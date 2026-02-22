"""GreetingConfig モデルのテスト"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from greeting.models import GreetingConfig


@pytest.mark.django_db
class TestGreetingConfig:
    """GreetingConfig モデルのテスト"""

    def test_create_config_with_required_fields(self):
        """必須フィールドで設定を作成できる"""
        config = GreetingConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            system_prompt="システムプロンプト",
        )

        assert config.id is not None
        assert config.name == "morning"
        assert config.display_name == "朝のあいさつ"
        assert config.system_prompt == "システムプロンプト"

    def test_name_is_unique(self):
        """name は一意でなければならない"""
        GreetingConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            system_prompt="システムプロンプト1",
        )

        # save()でfull_clean()が呼ばれるため、ValidationErrorまたはIntegrityErrorになる
        with pytest.raises((IntegrityError, ValidationError)):
            GreetingConfig.objects.create(
                name="morning",
                display_name="別の朝のあいさつ",
                system_prompt="システムプロンプト2",
            )

    def test_multiple_configs_allowed(self):
        """複数の設定を作成できる"""
        config1 = GreetingConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            system_prompt="システムプロンプト1",
        )
        config2 = GreetingConfig.objects.create(
            name="evening",
            display_name="夜のあいさつ",
            system_prompt="システムプロンプト2",
        )

        assert GreetingConfig.objects.count() == 2
        assert config1.name != config2.name

    # プレースホルダー設定のデフォルト値

    def test_placeholder_defaults(self):
        """プレースホルダー設定のデフォルト値が正しい"""
        config = GreetingConfig.objects.create(
            name="test",
            display_name="テスト",
            system_prompt="システムプロンプト",
        )

        assert config.use_weather is False
        assert config.use_events is False
        assert config.use_datetime is True

    def test_create_config_with_all_placeholders(self):
        """全プレースホルダーを有効にした設定を作成できる"""
        config = GreetingConfig.objects.create(
            name="full",
            display_name="フル設定",
            use_weather=True,
            use_events=True,
            use_datetime=True,
            area_code="130010",
            system_prompt="システムプロンプト",
        )

        assert config.use_weather is True
        assert config.use_events is True
        assert config.use_datetime is True

    # area_code バリデーション

    def test_area_code_required_when_use_weather_true(self):
        """use_weather=True の場合、area_code は必須"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="",
            system_prompt="システムプロンプト",
        )

        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    def test_area_code_not_required_when_use_weather_false(self):
        """use_weather=False の場合、area_code は不要"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=False,
            area_code="",
            system_prompt="システムプロンプト",
        )
        config.full_clean()  # ValidationError が発生しなければ成功

    def test_area_code_valid_6_digits(self):
        """area_code: 6桁の数字は有効"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="130010",
            system_prompt="システムプロンプト",
        )
        config.full_clean()

    def test_area_code_invalid_non_numeric(self):
        """area_code: 数字以外を含む場合はエラー"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="13001a",
            system_prompt="システムプロンプト",
        )
        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    def test_area_code_invalid_too_short(self):
        """area_code: 6桁未満の場合はエラー"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="12345",
            system_prompt="システムプロンプト",
        )
        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    # TTS設定

    def test_tts_enabled_default_is_false(self):
        """tts_enabled のデフォルト値は False"""
        config = GreetingConfig.objects.create(
            name="test",
            display_name="テスト",
            system_prompt="システムプロンプト",
        )

        assert config.tts_enabled is False

    def test_tts_options_default_values(self):
        """TTS オプションのデフォルト値が正しく設定される"""
        config = GreetingConfig.objects.create(
            name="test",
            display_name="テスト",
            system_prompt="システムプロンプト",
        )

        assert config.tts_model == ""
        assert config.tts_style == "Neutral"
        assert config.tts_style_weight == 1.0
        assert config.tts_speed == 1.0
        assert config.tts_sdp_ratio == 0.2
        assert config.tts_noise_scale == 0.6
        assert config.tts_noise_scale_w == 0.8

    def test_create_config_with_tts_enabled(self):
        """音声合成を有効にした設定を作成できる"""
        config = GreetingConfig.objects.create(
            name="test",
            display_name="テスト",
            system_prompt="システムプロンプト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_style_weight=1.5,
            tts_speed=1.2,
        )

        assert config.tts_enabled is True
        assert config.tts_model == "test_model"
        assert config.tts_style == "Happy"
        assert config.tts_style_weight == 1.5
        assert config.tts_speed == 1.2

    # get_tts_options() メソッド

    def test_get_tts_options_when_disabled(self):
        """get_tts_options(): TTS無効時は None を返す"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            system_prompt="システムプロンプト",
            tts_enabled=False,
        )
        assert config.get_tts_options() is None

    def test_get_tts_options_when_enabled(self):
        """get_tts_options(): TTS有効時は設定を辞書で返す"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            system_prompt="システムプロンプト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_style_weight=1.5,
            tts_speed=1.2,
            tts_sdp_ratio=0.3,
            tts_noise_scale=0.5,
            tts_noise_scale_w=0.7,
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
        assert options["format"] == "mp3"

    def test_get_tts_options_includes_format(self):
        """get_tts_options(): formatフィールドが含まれる"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            system_prompt="システムプロンプト",
            tts_enabled=True,
            tts_format="ogg",
        )
        options = config.get_tts_options()

        assert options["format"] == "ogg"

    def test_tts_format_default_is_mp3(self):
        """tts_format のデフォルト値は mp3"""
        config = GreetingConfig.objects.create(
            name="test_format",
            display_name="テスト",
            system_prompt="システムプロンプト",
        )

        assert config.tts_format == "mp3"

    def test_get_tts_options_model_empty_returns_none(self):
        """get_tts_options(): tts_model が空文字の場合は model が None"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            system_prompt="システムプロンプト",
            tts_enabled=True,
            tts_model="",
        )
        options = config.get_tts_options()

        assert options["model"] is None

    # __str__ と verbose_name

    def test_str_returns_display_name(self):
        """__str__ は display_name を返す"""
        config = GreetingConfig.objects.create(
            name="morning",
            display_name="朝のあいさつ",
            system_prompt="システムプロンプト",
        )

        assert str(config) == "朝のあいさつ"

    def test_verbose_name(self):
        """verbose_name が正しく設定されている"""
        assert GreetingConfig._meta.verbose_name == "挨拶設定"
        assert GreetingConfig._meta.verbose_name_plural == "挨拶設定"

    # save() でのバリデーション

    def test_save_validates_area_code_when_use_weather(self):
        """save(): use_weather=True で不正な area_code で保存するとエラー"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="invalid",
            system_prompt="システムプロンプト",
        )
        with pytest.raises(ValidationError) as exc_info:
            config.save()
        assert "area_code" in exc_info.value.message_dict

    def test_save_validates_area_code_required_when_use_weather(self):
        """save(): use_weather=True で area_code 未設定だとエラー"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            area_code="",
            system_prompt="システムプロンプト",
        )
        with pytest.raises(ValidationError) as exc_info:
            config.save()
        assert "area_code" in exc_info.value.message_dict

    # get_enabled_placeholders() メソッド

    def test_get_enabled_placeholders_all_disabled(self):
        """get_enabled_placeholders(): 全て無効の場合"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=False,
            use_events=False,
            use_datetime=False,
            system_prompt="システムプロンプト",
        )
        assert config.get_enabled_placeholders() == []

    def test_get_enabled_placeholders_all_enabled(self):
        """get_enabled_placeholders(): 全て有効の場合"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            use_events=True,
            use_datetime=True,
            area_code="130010",
            system_prompt="システムプロンプト",
        )
        placeholders = config.get_enabled_placeholders()
        assert "weather" in placeholders
        assert "events" in placeholders
        assert "datetime" in placeholders

    def test_get_enabled_placeholders_partial(self):
        """get_enabled_placeholders(): 一部有効の場合"""
        config = GreetingConfig(
            name="test",
            display_name="テスト",
            use_weather=True,
            use_events=False,
            use_datetime=True,
            area_code="130010",
            system_prompt="システムプロンプト",
        )
        placeholders = config.get_enabled_placeholders()
        assert "weather" in placeholders
        assert "events" not in placeholders
        assert "datetime" in placeholders
