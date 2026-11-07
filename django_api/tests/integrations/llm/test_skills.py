"""integrations.llm.skills のテスト（スキルの本文を Langfuse から取る。フォールバックはない）.

Langfuse は代役（`langfuse_prompts`。tests/conftest.py）にし、(プロンプト名, ラベル) で
入れた本文だけを返させる。
"""

import pytest

from integrations.langfuse.exceptions import LangfusePromptError, PromptUnavailableError
from integrations.llm.skills import resolve_skill_body
from tests.fixtures.factories import AgentSkillFactory, LangfusePromptRefFactory

MORNING_BODY = "天気と今日の予定に触れて、朝のあいさつをする"
# スキルの本文を置く Langfuse のプロンプト名（スキル名そのもの）
MORNING_PROMPT = "good-morning"
EMPTY_TEXTS = ["", " \n\t "]


@pytest.mark.unit
class TestResolveSkillBody:
    """resolve_skill_body（スキルの本文を Langfuse から取る。フォールバックはない）."""

    def test_resolve_skill_body_returns_stripped_body_of_prompt_with_skill_label(
        self, langfuse_prompts
    ):
        """スキル名と同じ名前のプロンプトをスキルのラベルで取り、前後の空白を除いて返す."""
        langfuse_prompts[(MORNING_PROMPT, "staging")] = f"\n  {MORNING_BODY}\n"
        langfuse_prompts[(MORNING_PROMPT, "production")] = "production の本文"
        skill = AgentSkillFactory.build(name="good-morning", label="staging")

        assert resolve_skill_body(skill) == MORNING_BODY

    @pytest.mark.parametrize("body", EMPTY_TEXTS)
    def test_resolve_skill_body_with_empty_body_raises_error_with_prompt_name(
        self, langfuse_prompts, body
    ):
        """本文が空（空白だけ）なら、プロンプト名を持つ PromptUnavailableError を送出する."""
        langfuse_prompts[(MORNING_PROMPT, "staging")] = body

        with pytest.raises(PromptUnavailableError) as exc_info:
            resolve_skill_body(AgentSkillFactory.build(name="good-morning"))

        assert (exc_info.value.ref_name, exc_info.value.reason) == (
            MORNING_PROMPT,
            "本文が空です",
        )

    def test_resolve_skill_body_without_prompt_for_label_raises_error_with_cause(
        self, langfuse_prompts
    ):
        """スキルのラベルのプロンプトがなければ PromptUnavailableError（ほかのラベルは使わない）.

        取得の失敗（LangfusePromptError）はそのまま出さず、原因（`__cause__`）として持つ。
        """
        langfuse_prompts[(MORNING_PROMPT, "production")] = MORNING_BODY
        skill = AgentSkillFactory.build(name="good-morning", label="staging")

        with pytest.raises(PromptUnavailableError) as exc_info:
            resolve_skill_body(skill)

        assert exc_info.value.ref_name == MORNING_PROMPT
        assert isinstance(exc_info.value.__cause__, LangfusePromptError)

    def test_resolve_skill_body_when_langfuse_unreachable_raises_error_with_reason(
        self, langfuse_unreachable
    ):
        """Langfuse に届かなければ PromptUnavailableError（理由に取得の失敗を書く）."""
        with pytest.raises(PromptUnavailableError, match=MORNING_PROMPT) as exc_info:
            resolve_skill_body(AgentSkillFactory.build(name="good-morning"))

        cause = exc_info.value.__cause__
        assert isinstance(cause, LangfusePromptError)
        assert exc_info.value.reason == str(cause)


@pytest.mark.integration
@pytest.mark.django_db
def test_resolve_skill_body_when_langfuse_unreachable_never_uses_ref_fallback(
    langfuse_unreachable,
):
    """Langfuse に届かなくても、同じ名前の参照（移行で残った旧スキルの参照など）の本文は使わない."""
    LangfusePromptRefFactory(
        name=MORNING_PROMPT,
        langfuse_prompt_name=MORNING_PROMPT,
        label="staging",
        fallback_text=MORNING_BODY,
    )

    with pytest.raises(PromptUnavailableError):
        resolve_skill_body(AgentSkillFactory(name="good-morning"))
