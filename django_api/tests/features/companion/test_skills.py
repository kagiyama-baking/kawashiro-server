"""スキル（CompanionSkill を実行ごとの遅延 capability にする）のテスト.

Langfuse からは切り離し、本文は参照のフォールバックテキストで解決する（`resolve_prompt` は
本物のまま通し、呼び出しだけを記録する）。モデルは台本（`ScriptedLLM`）で差し替え、
本番のプロファイルで `run_agent_sync` を通す。天気の地域は空にするので、ツールも外へ出ない。
"""

import threading
from collections.abc import Sequence
from unittest.mock import patch

import pytest
from pydantic_ai import AgentRunResult
from pydantic_ai.capabilities import AbstractCapability, Capability
from pydantic_ai.messages import (
    LoadCapabilityReturnPart,
    ModelMessage,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    ToolReturnPart,
)

from features.companion.agent import COMPANION_AGENT, CompanionDeps
from features.companion.exceptions import PromptUnavailableError
from features.companion.skills import (
    build_skill_capabilities,
    loaded_skill,
    resolve_required_prompt,
    skill_instructions,
)
from integrations.langfuse.client import resolve_prompt
from integrations.llm.exceptions import LLMOutputError
from integrations.llm.runtime import _LITELLM_PROFILE, run_agent_sync
from tests.fixtures.factories import (
    CompanionConfigFactory,
    CompanionSkillFactory,
    LangfusePromptRefFactory,
)
from tests.fixtures.llm import (
    RecordedRequest,
    ScriptedLLM,
    load_capability,
    make_llm_settings,
    tool_call,
)

SYSTEM_PROMPT = "システムプロンプト"
MORNING_BODY = "天気と今日の予定に触れて、朝のあいさつをする"
NIGHT_BODY = "明日の天気に触れて、おやすみのあいさつをする"
EMPTY_TEXTS = ["", " \n\t "]


def _run(
    llm: ScriptedLLM, capabilities: Sequence[AbstractCapability[CompanionDeps]]
) -> AgentRunResult:
    """台本のモデルで COMPANION_AGENT を 1 回実行する（システムプロンプトは実行の指示で渡す）."""
    with COMPANION_AGENT.override(model=llm.model):
        return run_agent_sync(
            COMPANION_AGENT,
            make_llm_settings("companion"),
            user_prompt="おはよう",
            instructions=SYSTEM_PROMPT,
            deps=CompanionDeps(area_code=""),
            capabilities=capabilities,
        )


def _scripted(*script: str | ModelResponse) -> ScriptedLLM:
    """本番のプロファイルで応答する台本（読み込んだ本文が会話途中の system で届く）."""
    return ScriptedLLM(*script, profile=_LITELLM_PROFILE)


def _catalog_entries(request: RecordedRequest) -> list[str]:
    """system に載ったスキルの一覧（カタログ）の項目行（`- 名前: 説明`）を順に返す.

    見出しと `<context>` の囲みは PydanticAI の定型文なので、ここでは見ない。
    """
    (catalog,) = [text for text in request.system_prompts if "load_capability" in text]
    return [line for line in catalog.splitlines() if line.startswith("- ")]


def _has_in_system(request: RecordedRequest, text: str) -> bool:
    """`text` がリクエストの system のどれかに入っているか."""
    return any(text in prompt for prompt in request.system_prompts)


def _sent(request: RecordedRequest) -> str:
    """リクエストで受け取ったもの全部（会話・指示・ツール定義）を 1 つの文字列にする."""
    return repr(request)


@pytest.fixture(autouse=True)
def _langfuse_unreachable():
    """Langfuse から切り離す（本文は参照のフォールバックテキストになる）."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.fixture
def resolutions():
    """スキルの本文の解決を（参照の識別名, 解決したスレッド）の順で記録する."""
    calls: list[tuple[str, int]] = []

    def record(ref, **variables):
        calls.append((ref.name, threading.get_ident()))
        return resolve_prompt(ref, **variables)

    with patch("features.companion.skills.resolve_prompt", side_effect=record):
        yield calls


@pytest.fixture
def skills(db):
    """名前順と逆に並べたスキル 2 件（おやすみ → おはよう）."""
    config = CompanionConfigFactory()
    return [
        CompanionSkillFactory(
            config=config,
            name="good-night",
            description="夜のあいさつ（「おやすみ」など）",
            prompt_ref__fallback_text=NIGHT_BODY,
        ),
        CompanionSkillFactory(
            config=config,
            name="good-morning",
            description="朝のあいさつ（「おはよう」など）",
            prompt_ref__fallback_text=MORNING_BODY,
        ),
    ]


@pytest.fixture
def morning_run(skills):
    """おはようのスキルを読み込んでから答える実行の、台本（受け取った内容）と結果."""
    llm = _scripted(load_capability("good-morning"), "おはよう！")
    result = _run(llm, build_skill_capabilities(skills))
    return llm, result


@pytest.mark.unit
class TestResolveRequiredPrompt:
    """resolve_required_prompt（本文が空なら読めた体で続けない）."""

    def test_resolve_required_prompt_with_text_returns_stripped_text(self):
        """前後の空白を除いた本文を返す."""
        ref = LangfusePromptRefFactory.build(
            name="companion-skill-good-morning", fallback_text=f"\n  {MORNING_BODY}\n"
        )

        assert resolve_required_prompt(ref) == MORNING_BODY

    @pytest.mark.parametrize("fallback_text", EMPTY_TEXTS)
    def test_resolve_required_prompt_with_empty_text_raises_error_with_ref_name(
        self, fallback_text
    ):
        """本文が空（空白だけ）なら、参照の識別名を持つ PromptUnavailableError を送出する.

        `resolve_prompt` は Langfuse から取れないと例外を出さずにフォールバックテキストへ落ちる。
        """
        ref = LangfusePromptRefFactory.build(
            name="companion-system", fallback_text=fallback_text
        )

        with pytest.raises(
            PromptUnavailableError, match="companion-system"
        ) as exc_info:
            resolve_required_prompt(ref)

        assert exc_info.value.ref_name == "companion-system"


@pytest.mark.unit
class TestSkillInstructions:
    """skill_instructions（スキルを指定したときに、本文を実行の指示に足す節にする）."""

    def test_skill_instructions_puts_stripped_body_under_heading(self):
        """見出しの下に、前後の空白を除いた本文を置く."""
        skill = CompanionSkillFactory.build(
            name="good-night",
            prompt_ref=LangfusePromptRefFactory.build(
                fallback_text=f"\n  {NIGHT_BODY}\n"
            ),
        )

        heading, blank, body = skill_instructions(skill).split("\n")

        assert heading.startswith("# ")
        assert blank == ""
        assert body == NIGHT_BODY

    @pytest.mark.parametrize("fallback_text", EMPTY_TEXTS)
    def test_skill_instructions_with_empty_body_raises_error_with_ref_name(
        self, fallback_text
    ):
        """本文が空なら、参照の識別名を持つ PromptUnavailableError を送出する."""
        skill = CompanionSkillFactory.build(
            name="good-night",
            prompt_ref=LangfusePromptRefFactory.build(
                name="companion-skill-good-night", fallback_text=fallback_text
            ),
        )

        with pytest.raises(PromptUnavailableError) as exc_info:
            skill_instructions(skill)

        assert exc_info.value.ref_name == "companion-skill-good-night"


@pytest.mark.unit
def test_build_skill_capabilities_without_skills_returns_empty_list():
    """スキルがなければ capability を作らない（一覧も load_capability も出ない）."""
    assert build_skill_capabilities([]) == []


@pytest.mark.integration
@pytest.mark.django_db
class TestBuildSkillCapabilities:
    """スキルの capability を実際の実行に渡したときの振る舞い."""

    def test_skill_capabilities_before_load_list_names_and_descriptions_in_given_order(
        self, morning_run
    ):
        """読み込む前の system には、スキル名と説明の一覧が渡した順で載る."""
        llm, _ = morning_run

        assert _catalog_entries(llm.requests[0]) == [
            "- good-night: 夜のあいさつ（「おやすみ」など）",
            "- good-morning: 朝のあいさつ（「おはよう」など）",
        ]

    def test_skill_capabilities_before_load_offer_load_capability_without_bodies(
        self, morning_run
    ):
        """読み込む前は load_capability を出し、どのスキルの本文もリクエストに入れない."""
        llm, _ = morning_run
        first = llm.requests[0]

        assert "load_capability" in {tool.name for tool in first.function_tools}
        assert MORNING_BODY not in _sent(first)
        assert NIGHT_BODY not in _sent(first)

    def test_skill_capabilities_after_load_send_only_loaded_body_as_system(
        self, morning_run
    ):
        """読み込むと、次のリクエストの system にそのスキルの本文だけが入る（発話には混ざらない）."""
        llm, _ = morning_run
        second = llm.requests[1]

        assert _has_in_system(second, MORNING_BODY)
        assert all(MORNING_BODY not in text for _, text in second.conversation)
        assert NIGHT_BODY not in _sent(second)

    def test_skill_capabilities_after_load_return_final_output(self, morning_run):
        """読み込んだ後の応答を出力として返す."""
        llm, result = morning_run

        assert len(llm.requests) == 2
        assert result.output == "おはよう！"

    def test_skill_capabilities_resolve_body_once_across_requests_after_load(
        self, skills, resolutions
    ):
        """読み込んだ後はリクエストのたびに本文を送るが、解決は実行ごとに 1 回だけ.

        読み込まなかったスキルの本文は解決しない（Langfuse へ取りに行かない）。
        """
        llm = _scripted(
            load_capability("good-morning"),
            tool_call("get_weather"),
            tool_call("get_weather", day=1),
            "おはよう！",
        )

        _run(llm, build_skill_capabilities(skills))

        after_load = llm.requests[1:]
        assert len(after_load) == 3
        assert all(_has_in_system(request, MORNING_BODY) for request in after_load)
        assert [name for name, _ in resolutions] == [skills[1].prompt_ref.name]

    def test_skill_capabilities_resolve_body_on_calling_thread(
        self, skills, resolutions
    ):
        """本文は呼び出し元のスレッドで解決する（呼び出し元の DB 接続を使う）."""
        llm = _scripted(load_capability("good-morning"), "おはよう！")

        _run(llm, build_skill_capabilities(skills))

        assert [thread for _, thread in resolutions] == [threading.get_ident()]

    def test_skill_capabilities_without_load_never_resolve_bodies(
        self, skills, resolutions
    ):
        """読み込まれなければ、どの本文も解決しない."""
        _run(_scripted("こんにちは"), build_skill_capabilities(skills))

        assert resolutions == []

    @pytest.mark.parametrize("fallback_text", EMPTY_TEXTS)
    def test_skill_capabilities_with_empty_body_raise_prompt_unavailable_error(
        self, resolutions, fallback_text
    ):
        """本文が空なら PromptUnavailableError をそのまま送出し、読めた体でモデルへ続けない.

        LLM の失敗（`translate_llm_errors` の LLMClientError）に変えず、ExceptionGroup にも包まない。
        """
        skill = CompanionSkillFactory(
            name="good-morning", prompt_ref__fallback_text=fallback_text
        )
        llm = _scripted(load_capability("good-morning"), "おはよう！")

        with pytest.raises(PromptUnavailableError) as exc_info:
            _run(llm, build_skill_capabilities([skill]))

        assert exc_info.value.ref_name == skill.prompt_ref.name
        assert len(llm.requests) == 1

    def test_loaded_skill_with_skill_capabilities_returns_loaded_skill_name(
        self, morning_run
    ):
        """スキルの capability を渡した実行の履歴から、読み込んだスキル名を返す."""
        _, result = morning_run

        assert loaded_skill(result.all_messages()) == "good-morning"


def _deferred(capability_id: str) -> Capability[CompanionDeps]:
    """本文が固定の遅延 capability（DB を使わないスキルの代わり）."""
    return Capability(
        id=capability_id,
        description=f"{capability_id} のときに使う",
        instructions=f"{capability_id} の本文",
        defer_loading=True,
    )


def _history(*script: str | ModelResponse) -> list[ModelMessage]:
    """スキル 2 件（good-morning / good-night）を渡して台本どおりに実行した履歴."""
    result = _run(
        _scripted(*script), [_deferred("good-morning"), _deferred("good-night")]
    )
    return result.all_messages()


def _parts(
    messages: Sequence[ModelMessage],
) -> list[ModelRequestPart | ModelResponsePart]:
    """履歴のパートを順に並べる."""
    return [part for message in messages for part in message.parts]


@pytest.mark.unit
class TestLoadedSkill:
    """loaded_skill（最初に読み込みに成功したスキル）."""

    def test_loaded_skill_after_successful_load_returns_its_name(self):
        """読み込みに成功したスキルの名前を返す."""
        messages = _history(load_capability("good-morning"), "おはよう！")

        assert loaded_skill(messages) == "good-morning"

    def test_loaded_skill_without_load_returns_none(self):
        """どのスキルも読み込まなければ None."""
        assert loaded_skill(_history("こんにちは")) is None

    def test_loaded_skill_with_unknown_name_only_returns_none(self):
        """不明な名前の読み込みは失敗なので数えない."""
        assert loaded_skill(_history(load_capability("good-evening"), "結論")) is None

    def test_loaded_skill_after_unknown_name_returns_later_successful_load(self):
        """不明な名前の読み込みは数えず、その後に成功した読み込みを返す.

        PydanticAI 2.64.0 では、不明な名前でも呼び出しは `LoadCapabilityCallPart` になるが、
        戻り値は再試行を求める普通の `ToolReturnPart`（outcome="retried"）のまま。
        """
        messages = _history(
            load_capability("good-evening"), load_capability("good-morning"), "結論"
        )

        retried = [
            (type(part), part.tool_name)
            for part in _parts(messages)
            if isinstance(part, ToolReturnPart) and part.outcome == "retried"
        ]
        assert retried == [(ToolReturnPart, "load_capability")]
        assert loaded_skill(messages) == "good-morning"

    def test_loaded_skill_with_two_successful_loads_returns_first(self):
        """2 つ読み込んだら、最初に読み込んだスキルを返す."""
        messages = _history(
            load_capability("good-night"), load_capability("good-morning"), "結論"
        )

        loads = [
            part
            for part in _parts(messages)
            if isinstance(part, LoadCapabilityReturnPart)
        ]
        assert len(loads) == 2
        assert loaded_skill(messages) == "good-night"


@pytest.mark.unit
def test_skill_load_failing_twice_in_a_row_fails_run_with_llm_output_error():
    """読み込みに続けて 2 回失敗すると実行が失敗する（再試行は PydanticAI の既定で 1 回まで）."""
    with pytest.raises(LLMOutputError, match="load_capability"):
        _history(
            load_capability("good-evening"), load_capability("good-afternoon"), "結論"
        )
