"""MorningGreetingConfig モデルのテスト"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from greeting.models import MorningGreetingConfig


@pytest.mark.django_db
class TestMorningGreetingConfig:
    """MorningGreetingConfig モデルのテスト"""

    def test_create_config_with_required_fields(self):
        """必須フィールドで設定を作成できる"""
        config = MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )

        assert config.id is not None
        assert config.area_code == "130010"
        assert config.system_prompt == "システムプロンプト"
        assert config.user_prompt == "ユーザープロンプト"

    def test_only_one_config_allowed(self):
        """設定は1つしか作成できない（シングルトン）"""
        MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="システムプロンプト1",
            user_prompt="ユーザープロンプト1",
        )

        # save()でfull_clean()が呼ばれるため、ValidationErrorになる
        with pytest.raises((IntegrityError, ValidationError)):
            MorningGreetingConfig.objects.create(
                area_code="270000",
                system_prompt="システムプロンプト2",
                user_prompt="ユーザープロンプト2",
            )

    def test_tts_enabled_default_is_false(self):
        """tts_enabled のデフォルト値は False"""
        config = MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )

        assert config.tts_enabled is False

    def test_tts_options_default_values(self):
        """TTS オプションのデフォルト値が正しく設定される"""
        config = MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
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
        config = MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
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

    def test_str_returns_verbose_name(self):
        """__str__ は「朝のあいさつ設定」を返す"""
        config = MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )

        assert str(config) == "朝のあいさつ設定"

    def test_verbose_name(self):
        """verbose_name が正しく設定されている"""
        assert MorningGreetingConfig._meta.verbose_name == "朝のあいさつ設定"
        assert MorningGreetingConfig._meta.verbose_name_plural == "朝のあいさつ設定"

    def test_get_solo_creates_if_not_exists(self):
        """get_solo() は設定がなければ None を返す"""
        config = MorningGreetingConfig.get_solo()
        assert config is None

    def test_get_solo_returns_existing(self):
        """get_solo() は既存の設定を返す"""
        created = MorningGreetingConfig.objects.create(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )

        config = MorningGreetingConfig.get_solo()
        assert config.id == created.id

    # area_code バリデーション

    def test_area_code_valid_6_digits(self):
        """area_code: 6桁の数字は有効"""
        config = MorningGreetingConfig(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )
        config.full_clean()  # ValidationError が発生しなければ成功

    def test_area_code_invalid_non_numeric(self):
        """area_code: 数字以外を含む場合はエラー"""
        config = MorningGreetingConfig(
            area_code="13001a",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )
        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    def test_area_code_invalid_too_short(self):
        """area_code: 6桁未満の場合はエラー"""
        config = MorningGreetingConfig(
            area_code="12345",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )
        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    def test_area_code_invalid_too_long(self):
        """area_code: 6桁より長い場合はエラー"""
        config = MorningGreetingConfig(
            area_code="1234567",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )
        with pytest.raises(ValidationError) as exc_info:
            config.full_clean()
        assert "area_code" in exc_info.value.message_dict

    # get_tts_options() メソッド

    def test_get_tts_options_when_disabled(self):
        """get_tts_options(): TTS無効時は None を返す"""
        config = MorningGreetingConfig(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
            tts_enabled=False,
        )
        assert config.get_tts_options() is None

    def test_get_tts_options_when_enabled(self):
        """get_tts_options(): TTS有効時は設定を辞書で返す"""
        config = MorningGreetingConfig(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
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

    def test_get_tts_options_model_empty_returns_none(self):
        """get_tts_options(): tts_model が空文字の場合は model が None"""
        config = MorningGreetingConfig(
            area_code="130010",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
            tts_enabled=True,
            tts_model="",
        )
        options = config.get_tts_options()

        assert options["model"] is None

    # save() でのバリデーション

    def test_save_validates_area_code(self):
        """save(): 不正な area_code で保存するとエラー"""
        config = MorningGreetingConfig(
            area_code="invalid",
            system_prompt="システムプロンプト",
            user_prompt="ユーザープロンプト",
        )
        with pytest.raises(ValidationError) as exc_info:
            config.save()
        assert "area_code" in exc_info.value.message_dict
