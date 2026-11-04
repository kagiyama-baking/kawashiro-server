"""Companion の設定モデル（CompanionConfig / CompanionSkill）のテスト."""

import inspect

import pytest
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import ProtectedError
from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import UserError

from features.companion.models import (
    RESERVED_SKILL_NAMES,
    CompanionConfig,
    CompanionSkill,
)
from integrations.llm.runtime import run_agent_sync
from integrations.tts.client import TTSClient
from tests.fixtures.factories import (
    CompanionConfigFactory,
    CompanionSkillFactory,
    LangfusePromptRefFactory,
)
from tests.fixtures.llm import ScriptedLLM, make_llm_settings


def _unsaved_config(**fields) -> CompanionConfig:
    """保存前の設定（指定しない項目は正しい値）."""
    return CompanionConfig(
        system_prompt_ref=LangfusePromptRefFactory(name="companion-system"),
        **{"name": "main", **fields},
    )


def _unsaved_skill(config: CompanionConfig | None = None, **fields) -> CompanionSkill:
    """保存前のスキル（指定しない項目は正しい値）."""
    return CompanionSkill(
        config=config or CompanionConfigFactory(name="main"),
        prompt_ref=LangfusePromptRefFactory(name="companion-skill-body"),
        **{
            "name": "good-morning",
            "description": "朝のあいさつ（「おはよう」など）に使う",
            **fields,
        },
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
class TestCompanionSkillValidation:
    """スキルの入力チェック（名前は capability の id になる）."""

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("good-morning", id="kebab_case"),
            pytest.param("a", id="single_char"),
            pytest.param("night2", id="with_digits"),
            pytest.param("a" * 64, id="64_chars"),
        ],
    )
    def test_skill_name_with_valid_value_passes_validation(self, name):
        """英小文字・数字をハイフンでつないだ 64 字以内の名前."""
        _unsaved_skill(name=name).full_clean()

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("Good", id="uppercase"),
            pytest.param("good_morning", id="underscore"),
            pytest.param("good:morning", id="colon"),
            pytest.param("-good", id="leading_hyphen"),
            pytest.param("good-", id="trailing_hyphen"),
            pytest.param("good--morning", id="consecutive_hyphens"),
            pytest.param("good morning", id="space"),
            pytest.param("おはよう", id="non_ascii"),
            pytest.param("good-morning\n", id="trailing_newline"),
            pytest.param("deferred_capabilities", id="catalog_reserved_id"),
            pytest.param("a" * 65, id="65_chars"),
            pytest.param("", id="empty"),
        ],
    )
    def test_skill_name_with_invalid_value_raises_validation_error(self, name):
        """命名規則に合わない名前は拒む."""
        with pytest.raises(ValidationError) as exc_info:
            _unsaved_skill(name=name).full_clean()

        assert "name" in exc_info.value.message_dict

    def test_skill_name_instrumentation_raises_validation_error(self):
        """毎回の実行に入る組み込みの capability と同じ id（instrumentation）は拒む."""
        with pytest.raises(ValidationError) as exc_info:
            _unsaved_skill(name="instrumentation").full_clean()

        assert "name" in exc_info.value.message_dict

    def test_skill_description_with_1024_chars_passes_validation(self):
        """説明は 1024 字まで."""
        _unsaved_skill(description="あ" * 1024).full_clean()

    def test_skill_description_with_1025_chars_raises_validation_error(self):
        """説明が 1025 字なら拒む."""
        with pytest.raises(ValidationError) as exc_info:
            _unsaved_skill(description="あ" * 1025).full_clean()

        assert "description" in exc_info.value.message_dict

    def test_skill_description_empty_raises_validation_error(self):
        """説明は必須（モデルはこれを読んでスキルを選ぶ）."""
        with pytest.raises(ValidationError) as exc_info:
            _unsaved_skill(description="").full_clean()

        assert "description" in exc_info.value.message_dict

    def test_skill_name_duplicate_in_same_config_raises_validation_error(self):
        """同じ設定の中でスキル名は一意."""
        existing = CompanionSkillFactory(name="good-morning")

        with pytest.raises(ValidationError) as exc_info:
            _unsaved_skill(config=existing.config, name="good-morning").full_clean()

        assert NON_FIELD_ERRORS in exc_info.value.message_dict

    def test_skill_name_duplicate_in_other_config_passes_validation(self):
        """別の設定なら同じスキル名を使える."""
        CompanionSkillFactory(name="good-morning")

        _unsaved_skill(
            config=CompanionConfigFactory(name="other"), name="good-morning"
        ).full_clean()

    def test_skill_save_with_invalid_value_raises_validation_error(self):
        """save() は保存の前に full_clean() で拒む."""
        with pytest.raises(ValidationError):
            _unsaved_skill(name="Good").save()

        assert not CompanionSkill.objects.exists()


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(RESERVED_SKILL_NAMES))
def test_reserved_skill_name_as_capability_id_fails_agent_run(name):
    """予約したスキル名を capability の id にすると、実行そのものが失敗する（予約の根拠）.

    `integrations/llm/apps.py` の `Agent.instrument_all` で、どの実行にも
    Instrumentation（id: instrumentation）が入る。PydanticAI の更新で衝突しなく
    なったらこのテストが落ちるので、予約を見直す。
    """
    agent = Agent(name="reserved-skill-name")
    skill = Capability(
        id=name, description="説明", instructions="本文", defer_loading=True
    )

    with (
        agent.override(model=ScriptedLLM("こんにちは").model),
        pytest.raises(UserError, match=f"Capability id {name!r}"),
    ):
        run_agent_sync(
            agent,
            make_llm_settings("companion"),
            user_prompt="おはよう",
            capabilities=[skill],
        )


@pytest.mark.integration
@pytest.mark.django_db
class TestCompanionSkillRelations:
    """スキルと設定・プロンプト参照のつながり."""

    def test_skill_is_enabled_default_is_true(self):
        """スキルは既定で有効."""
        assert CompanionSkillFactory().is_enabled is True

    def test_skill_str_returns_name(self):
        """表示はスキル名."""
        assert str(CompanionSkillFactory(name="good-night")) == "good-night"

    def test_config_skills_are_ordered_by_name(self):
        """設定のスキルは名前順に並ぶ."""
        config = CompanionConfigFactory()
        for name in ("welcome-home", "good-night", "good-morning"):
            CompanionSkillFactory(config=config, name=name)

        assert [skill.name for skill in config.skills.all()] == [
            "good-morning",
            "good-night",
            "welcome-home",
        ]

    def test_config_delete_with_skills_deletes_skills(self):
        """設定を消すとそのスキルも消える."""
        skill = CompanionSkillFactory()

        skill.config.delete()

        assert not CompanionSkill.objects.exists()

    def test_skill_prompt_ref_delete_while_referenced_raises_protected_error(self):
        """スキルが参照している本文の参照は消せない."""
        skill = CompanionSkillFactory()

        with pytest.raises(ProtectedError):
            skill.prompt_ref.delete()
