"""Agent Skills（AgentSkill。全エージェントで共有するスキル）のモデルのテスト."""

import pytest
from django.core.exceptions import ValidationError
from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import UserError

from integrations.llm.models import RESERVED_SKILL_NAMES, AgentSkill
from integrations.llm.runtime import run_agent_sync
from tests.fixtures.factories import AgentSkillFactory
from tests.fixtures.llm import ScriptedLLM, make_llm_settings


def _unsaved_skill(**fields) -> AgentSkill:
    """保存前のスキル（指定しない項目は正しい値）."""
    return AgentSkill(
        **{
            "name": "good-morning",
            "description": "朝のあいさつ（「おはよう」など）に使う",
            **fields,
        }
    )


@pytest.mark.unit
class TestAgentSkillLocation:
    """モデルの置き場所（admin のグループ）と表."""

    def test_skill_app_label_is_llm_config(self):
        """llm_config アプリのモデル（admin では LLM の設定と同じグループに出る）."""
        assert AgentSkill._meta.app_label == "llm_config"

    def test_skill_db_table_is_table_created_by_companion(self):
        """表は companion の migration が作った companion_agentskill のまま（状態だけ移した）."""
        assert AgentSkill._meta.db_table == "companion_agentskill"


@pytest.mark.integration
@pytest.mark.django_db
class TestAgentSkillValidation:
    """スキルの入力チェック（名前は capability の id と Langfuse のプロンプト名になる）."""

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

    def test_skill_name_duplicate_raises_validation_error(self):
        """スキル名は全体で一意（Langfuse のプロンプト名をスキル名から決めるため）."""
        AgentSkillFactory(name="good-morning")

        with pytest.raises(ValidationError) as exc_info:
            _unsaved_skill(name="good-morning").full_clean()

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

    def test_skill_label_empty_raises_validation_error(self):
        """ラベルは必須（本文を取る Langfuse のラベル）."""
        with pytest.raises(ValidationError) as exc_info:
            _unsaved_skill(label="").full_clean()

        assert "label" in exc_info.value.message_dict

    def test_skill_save_with_invalid_value_raises_validation_error(self):
        """save() は保存の前に full_clean() で拒む."""
        with pytest.raises(ValidationError):
            _unsaved_skill(name="Good").save()

        assert not AgentSkill.objects.exists()

    def test_skills_are_ordered_by_name(self):
        """スキルは名前順に並ぶ."""
        for name in ("welcome-home", "good-night", "good-morning"):
            AgentSkillFactory(name=name)

        assert [skill.name for skill in AgentSkill.objects.all()] == [
            "good-morning",
            "good-night",
            "welcome-home",
        ]


@pytest.mark.unit
class TestAgentSkillAttributes:
    """スキルの既定値・本文のプロンプト名・表示."""

    def test_skill_defaults_are_production_label_and_enabled(self):
        """ラベルは既定で production、スキルは既定で有効."""
        skill = _unsaved_skill()

        assert (skill.label, skill.is_enabled) == ("production", True)

    def test_skill_prompt_name_is_companion_skill_prefix_and_name(self):
        """本文の Langfuse のプロンプト名は companion-skill-<スキル名>."""
        assert _unsaved_skill(name="good-night").prompt_name == (
            "companion-skill-good-night"
        )

    def test_skill_str_shows_name_prompt_name_and_label(self):
        """表示はスキル名と、本文のプロンプト名@ラベル（設定の選択欄にそのまま出る）."""
        skill = _unsaved_skill(name="good-night", label="staging")

        assert str(skill) == "good-night（companion-skill-good-night@staging）"


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
