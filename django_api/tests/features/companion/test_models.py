"""Companion の設定モデル（CompanionConfig とスキルの選択）のテスト.

スキル（AgentSkill）そのもののテストは tests/integrations/llm/test_agent_skill.py。
"""

import inspect

import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from features.companion.models import CompanionConfig
from integrations.llm.models import AgentSkill
from integrations.tts.client import TTSClient
from tests.fixtures.factories import (
    AgentSkillFactory,
    CompanionConfigFactory,
    LangfusePromptRefFactory,
)


def _unsaved_config(**fields) -> CompanionConfig:
    """保存前の設定（指定しない項目は正しい値）."""
    return CompanionConfig(
        system_prompt_ref=LangfusePromptRefFactory(name="companion-system"),
        **{"name": "main", **fields},
    )


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionConfigActivation:
    """有効にできる設定は 1 つだけ."""

    def test_config_save_as_active_deactivates_other_configs(self):
        """有効にして保存すると、ほかの有効な設定が無効になる."""
        first = CompanionConfigFactory(is_active=True)
        second = CompanionConfigFactory(is_active=True)

        first.refresh_from_db()
        assert first.is_active is False
        assert second.is_active is True

    def test_config_save_as_inactive_keeps_active_config(self):
        """無効のまま保存しても、有効な設定はそのまま."""
        active = CompanionConfigFactory(is_active=True)
        CompanionConfigFactory(is_active=False)

        active.refresh_from_db()
        assert active.is_active is True

    def test_get_active_config_with_active_config_returns_it(self):
        """有効な設定を返す."""
        CompanionConfigFactory(is_active=False)
        active = CompanionConfigFactory(is_active=True)

        assert CompanionConfig.objects.get_active_config() == active

    def test_get_active_config_without_active_config_raises_does_not_exist(self):
        """有効な設定がなければ DoesNotExist."""
        CompanionConfigFactory(is_active=False)

        with pytest.raises(CompanionConfig.DoesNotExist):
            CompanionConfig.objects.get_active_config()

    def test_get_active_config_with_active_config_prefetches_system_prompt_ref(
        self, django_assert_num_queries
    ):
        """システムプロンプトの参照は同じクエリで読む（追加のクエリなし）."""
        CompanionConfigFactory(
            is_active=True,
            system_prompt_ref=LangfusePromptRefFactory(name="companion-system"),
        )

        with django_assert_num_queries(1):
            config = CompanionConfig.objects.get_active_config()
            assert config.system_prompt_ref.name == "companion-system"

    def test_config_str_when_active_marks_active(self):
        """有効な設定は名前に「（有効）」が付く."""
        assert str(_unsaved_config(name="main", is_active=True)) == "main（有効）"

    def test_config_str_when_inactive_returns_name(self):
        """無効な設定は名前だけ."""
        assert str(_unsaved_config(name="main", is_active=False)) == "main"


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionConfigValidation:
    """設定の入力チェック（save() でも full_clean() が走る）."""

    @pytest.mark.parametrize(
        "area_code",
        [
            pytest.param("", id="empty_means_no_weather"),
            pytest.param("130010", id="six_digits"),
        ],
    )
    def test_config_area_code_with_valid_value_passes_validation(self, area_code):
        """予報区コードは空か 6 桁の数字."""
        _unsaved_config(area_code=area_code).full_clean()

    @pytest.mark.parametrize(
        "area_code",
        [
            pytest.param("13001a", id="non_numeric"),
            pytest.param("12345", id="five_digits"),
            pytest.param("1300100", id="seven_digits"),
            pytest.param("１３００１０", id="full_width_digits"),
            pytest.param("130010\n", id="trailing_newline"),
        ],
    )
    def test_config_area_code_with_invalid_value_raises_validation_error(
        self, area_code
    ):
        """6 桁の半角数字でなければ拒む（全角数字・末尾の改行も）."""
        with pytest.raises(ValidationError) as exc_info:
            _unsaved_config(area_code=area_code).full_clean()

        assert "area_code" in exc_info.value.message_dict

    def test_config_rate_limit_default_is_10(self):
        """回数の上限は、指定しなければ 1 分あたり 10 回."""
        config = CompanionConfigFactory()

        config.refresh_from_db()
        assert config.rate_limit == 10

    def test_config_rate_limit_with_one_passes_validation(self):
        """回数の上限は 1 から."""
        _unsaved_config(rate_limit=1).full_clean()

    def test_config_rate_limit_with_zero_raises_validation_error(self):
        """回数の上限 0 は拒む."""
        with pytest.raises(ValidationError) as exc_info:
            _unsaved_config(rate_limit=0).full_clean()

        assert "rate_limit" in exc_info.value.message_dict

    def test_config_name_duplicate_raises_validation_error(self):
        """設定名は一意."""
        CompanionConfigFactory(name="main")

        with pytest.raises(ValidationError) as exc_info:
            _unsaved_config(name="main").full_clean()

        assert "name" in exc_info.value.message_dict

    def test_config_save_with_invalid_value_raises_validation_error(self):
        """save() は保存の前に full_clean() で拒む."""
        with pytest.raises(ValidationError):
            _unsaved_config(area_code="12345").save()

        assert not CompanionConfig.objects.exists()

    def test_system_prompt_ref_delete_while_referenced_raises_protected_error(self):
        """設定が参照しているシステムプロンプトの参照は消せない."""
        config = CompanionConfigFactory()

        with pytest.raises(ProtectedError):
            config.system_prompt_ref.delete()


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionConfigTTSOptions:
    """音声合成の設定を TTSClient.synthesize の引数にまとめる."""

    def test_config_get_tts_options_when_disabled_returns_none(self):
        """音声合成が無効なら None（音声を作らない）."""
        assert _unsaved_config(tts_enabled=False).get_tts_options() is None

    def test_config_get_tts_options_when_enabled_returns_all_settings(self):
        """有効なら全項目を返す."""
        config = _unsaved_config(
            tts_enabled=True,
            tts_model="hiroki",
            tts_style="Happy",
            tts_style_weight=1.5,
            tts_speed=1.2,
            tts_sdp_ratio=0.3,
            tts_noise_scale=0.5,
            tts_noise_scale_w=0.7,
            tts_format="mp3",
        )

        assert config.get_tts_options() == {
            "model": "hiroki",
            "style": "Happy",
            "style_weight": 1.5,
            "speed": 1.2,
            "sdp_ratio": 0.3,
            "noise_scale": 0.5,
            "noise_scale_w": 0.7,
            "format": "mp3",
        }

    def test_config_get_tts_options_with_empty_model_returns_none_model(self):
        """モデル名が空なら None（SBV2 側の既定のモデル）."""
        options = _unsaved_config(tts_enabled=True, tts_model="").get_tts_options()

        assert options["model"] is None

    def test_config_get_tts_options_keys_match_synthesize_keyword_arguments(self):
        """キーは TTSClient.synthesize のキーワード引数（text 以外）と同じ."""
        keywords = set(inspect.signature(TTSClient.synthesize).parameters) - {
            "self",
            "text",
        }

        assert set(_unsaved_config(tts_enabled=True).get_tts_options()) == keywords


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionConfigSkills:
    """設定とスキル（設定は登録済みのスキルから使うものを選ぶ）."""

    def test_config_skills_are_ordered_by_name(self):
        """設定で選んだスキルは名前順に並ぶ（選んだ順ではない）."""
        config = CompanionConfigFactory(
            skills=[
                AgentSkillFactory(name=name)
                for name in ("welcome-home", "good-night", "good-morning")
            ]
        )

        assert [skill.name for skill in config.skills.all()] == [
            "good-morning",
            "good-night",
            "welcome-home",
        ]

    def test_skill_selected_by_two_configs_is_shared(self):
        """1 つのスキルを 2 つの設定で選べる（設定ごとに登録し直さない）."""
        skill = AgentSkillFactory(name="good-morning")
        first = CompanionConfigFactory(skills=[skill])
        second = CompanionConfigFactory(skills=[skill])

        assert list(first.skills.all()) == list(second.skills.all()) == [skill]
        assert set(skill.companion_configs.all()) == {first, second}

    def test_config_delete_keeps_selected_skills(self):
        """設定を消しても、選んでいたスキルは残る."""
        skill = AgentSkillFactory(name="good-morning")
        config = CompanionConfigFactory(skills=[skill])

        config.delete()

        assert list(AgentSkill.objects.all()) == [skill]

    def test_skill_delete_removes_it_from_config_selection(self):
        """スキルを消すと、選んでいた設定の選択から外れる（設定は残る）."""
        morning = AgentSkillFactory(name="good-morning")
        night = AgentSkillFactory(name="good-night")
        config = CompanionConfigFactory(skills=[morning, night])

        morning.delete()

        assert list(CompanionConfig.objects.get(pk=config.pk).skills.all()) == [night]
