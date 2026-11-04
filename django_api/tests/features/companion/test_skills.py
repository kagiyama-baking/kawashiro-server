"""スキル（AgentSkill を実行ごとの遅延 capability にする）のテスト.

Langfuse は代役（`langfuse_prompts`。conftest）にし、スキルの本文は (プロンプト名, ラベル) で
入れたものを返させる（`fetch_text_prompt` は本物のまま通し、呼び出しだけを記録する）。
モデルは台本（`ScriptedLLM`）で差し替え、本番のプロファイルで `run_agent_sync` を通す。
天気の地域は空にするので、ツールも外へ出ない。
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
    resolve_skill_body,
    skill_instructions,
)
from integrations.langfuse.client import fetch_text_prompt
from integrations.langfuse.exceptions import LangfusePromptError
from integrations.llm.exceptions import LLMOutputError
from integrations.llm.runtime import _LITELLM_PROFILE, run_agent_sync
from tests.fixtures.factories import AgentSkillFactory, LangfusePromptRefFactory
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
# スキルの本文を置く Langfuse のプロンプト名（スキル名そのもの）
MORNING_PROMPT = "good-morning"
NIGHT_PROMPT = "good-night"
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


@pytest.fixture
def fetches():
    """スキルの本文の取得を（プロンプト名, ラベル, 取得したスレッド）の順で記録する."""
    calls: list[tuple[str, str, int]] = []

    def record(name, *, label):
        calls.append((name, label, threading.get_ident()))
        return fetch_text_prompt(name, label=label)

    with patch("features.companion.skills.fetch_text_prompt", side_effect=record):
        yield calls


@pytest.fixture
def skills(langfuse_prompts):
    """名前順と逆に並べたスキル 2 件（おやすみ → おはよう。本文は staging に置く）."""
    langfuse_prompts[(NIGHT_PROMPT, "staging")] = NIGHT_BODY
    langfuse_prompts[(MORNING_PROMPT, "staging")] = MORNING_BODY
    return [
        AgentSkillFactory.build(
            name="good-night", description="夜のあいさつ（「おやすみ」など）"
        ),
        AgentSkillFactory.build(
            name="good-morning", description="朝のあいさつ（「おはよう」など）"
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
    """resolve_required_prompt（システムプロンプト。本文が空なら読めた体で続けない）."""

    def test_resolve_required_prompt_with_text_returns_stripped_text(self):
        """前後の空白を除いた本文を返す."""
        ref = LangfusePromptRefFactory.build(
            name="companion-system", fallback_text=f"\n  {SYSTEM_PROMPT}\n"
        )

        assert resolve_required_prompt(ref) == SYSTEM_PROMPT

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

        assert (exc_info.value.ref_name, exc_info.value.reason) == (
            "companion-system",
            "本文が空です",
        )


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


@pytest.mark.unit
class TestSkillInstructions:
    """skill_instructions（スキルを指定したときに、本文を実行の指示に足す節にする）."""

    def test_skill_instructions_puts_stripped_body_under_heading(
        self, langfuse_prompts
    ):
        """見出しの下に、前後の空白を除いた本文を置く."""
        langfuse_prompts[(NIGHT_PROMPT, "staging")] = f"\n  {NIGHT_BODY}\n"

        heading, blank, body = skill_instructions(
            AgentSkillFactory.build(name="good-night")
        ).split("\n")

        assert heading.startswith("# ")
        assert blank == ""
        assert body == NIGHT_BODY

    @pytest.mark.parametrize("body", EMPTY_TEXTS)
    def test_skill_instructions_with_empty_body_raises_error_with_prompt_name(
        self, langfuse_prompts, body
    ):
        """本文が空なら、プロンプト名を持つ PromptUnavailableError を送出する."""
        langfuse_prompts[(NIGHT_PROMPT, "staging")] = body

        with pytest.raises(PromptUnavailableError) as exc_info:
            skill_instructions(AgentSkillFactory.build(name="good-night"))

        assert exc_info.value.ref_name == NIGHT_PROMPT


@pytest.mark.unit
def test_build_skill_capabilities_without_skills_returns_empty_list():
    """スキルがなければ capability を作らない（一覧も load_capability も出ない）."""
    assert build_skill_capabilities([]) == []


@pytest.mark.unit
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

    def test_skill_capabilities_fetch_body_once_with_skill_label_after_load(
        self, skills, fetches
    ):
        """読み込んだ後はリクエストのたびに本文を送るが、取るのは実行ごとに 1 回だけ.

        取るのは読み込んだスキルのプロンプトを、そのスキルのラベルで。読み込まなかった
        スキルの本文は取りに行かない。
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
        assert [(name, label) for name, label, _ in fetches] == [
            (MORNING_PROMPT, "staging")
        ]

    def test_skill_capabilities_fetch_body_on_calling_thread(self, skills, fetches):
        """本文は呼び出し元のスレッドで取る（システムプロンプトと同じスレッド）."""
        llm = _scripted(load_capability("good-morning"), "おはよう！")

        _run(llm, build_skill_capabilities(skills))

        assert [thread for _, _, thread in fetches] == [threading.get_ident()]

    def test_skill_capabilities_without_load_never_fetch_bodies(self, skills, fetches):
        """読み込まれなければ、どの本文も取りに行かない."""
        _run(_scripted("こんにちは"), build_skill_capabilities(skills))

        assert fetches == []

    @pytest.mark.parametrize(
        "body", [*EMPTY_TEXTS, None], ids=["empty", "whitespace", "unregistered"]
    )
    def test_skill_capabilities_with_unavailable_body_raise_prompt_unavailable_error(
        self, langfuse_prompts, body
    ):
        """本文が空か取れなければ PromptUnavailableError をそのまま送出し、読めた体で続けない.

        LLM の失敗（`translate_llm_errors` の LLMClientError）に変えず、ExceptionGroup にも包まない。
        """
        if body is not None:
            langfuse_prompts[(MORNING_PROMPT, "staging")] = body
        llm = _scripted(load_capability("good-morning"), "おはよう！")

        with pytest.raises(PromptUnavailableError) as exc_info:
            _run(
                llm,
                build_skill_capabilities(
                    [AgentSkillFactory.build(name="good-morning")]
                ),
            )

        assert exc_info.value.ref_name == MORNING_PROMPT
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
