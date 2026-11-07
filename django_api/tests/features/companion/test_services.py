"""Companion の実行サービス（run_companion）のテスト.

モデルは台本（`ScriptedLLM`）を本番のプロファイルで差し替え、`run_agent_sync` を通す。
LLM の接続設定は DB を読まないテスト用のもの（サービス名は呼び出しのまま）にする。Langfuse は
代役（conftest の `langfuse_prompts`）にし、システムプロンプトとスキルの本文は (プロンプト名,
ラベル) で入れたものを返させる。音声合成と祝日・天気のクライアントは差し替えるので、外へは出ない。
"""

import logging
from datetime import UTC, datetime
from unittest.mock import call, patch

import pytest

from features.companion.agent import COMPANION_AGENT, response_policy
from features.companion.exceptions import (
    CompanionNotConfiguredError,
    UnknownSkillError,
)
from features.companion.models import CompanionConfig
from features.companion.services import (
    REQUEST_LIMIT,
    TOOL_CALLS_LIMIT,
    TOOL_RETRIES,
    CompanionReply,
    run_companion,
)
from features.companion.skills import skill_instructions
from integrations.langfuse.exceptions import PromptUnavailableError
from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMOutputError,
    LLMTimeoutError,
)
from integrations.llm.runtime import _LITELLM_PROFILE
from integrations.tts.client import TTSResult
from integrations.tts.exceptions import TTSNetworkError
from tests.fixtures.factories import AgentSkillFactory, CompanionConfigFactory
from tests.fixtures.llm import (
    RecordedRequest,
    ScriptedLLM,
    load_capability,
    make_llm_settings,
    slow_model,
    tool_call,
    tool_calls,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

SERVICES = "features.companion.services"
LANGFUSE_CLIENT = "integrations.langfuse.client"
AREA_CODE = "130010"
# 設定のシステムプロンプト（Langfuse の text プロンプトの名前と本文。ラベルは production）
SYSTEM_PROMPT_NAME = "companion-test-system"
SYSTEM_PROMPT = "システムプロンプト"
MORNING_BODY = "天気と今日の予定に触れて、朝のあいさつをする"
NIGHT_BODY = "明日の天気に触れて、おやすみのあいさつをする"
HOME_BODY = "おかえりのあいさつをする"
EMPTY_TEXTS = ["", " \n\t "]
# 本文に漏れたツール呼び出しの書式（開発の実機で Kimi K2.5 が返した本文そのもの）
LEAKED_TOOL_CALL = '<parameter name="id">good-morning</parameter>'
AUDIO = TTSResult(
    audio_data=b"RIFF-test-audio", content_type="audio/mpeg", format="mp3"
)


@pytest.fixture(autouse=True)
def llm_settings():
    """LLM の接続設定を DB から読まず、呼ばれたサービス名のテスト用の設定を返す."""
    with patch(f"{SERVICES}.get_llm_settings", side_effect=make_llm_settings) as mocked:
        yield mocked


@pytest.fixture(autouse=True)
def tts_client():
    """音声合成のクライアント（クラス）を差し替える（合成すると AUDIO を返す）."""
    with patch(f"{SERVICES}.TTSClient", autospec=True) as cls:
        cls.return_value.synthesize.return_value = AUDIO
        yield cls


@pytest.fixture(autouse=True)
def _no_holiday_lookup():
    """get_datetime から祝日 API を呼ばない（祝日なしで答える）."""
    with patch("features.companion.agent.HolidayClient", autospec=True) as cls:
        cls.return_value.get_holiday_name.return_value = None
        yield


def _skill(langfuse_prompts, name: str, body: str, **fields):
    """スキルを登録し、本文を Langfuse の代役にスキルのラベルで置く."""
    skill = AgentSkillFactory(name=name, **fields)
    langfuse_prompts[(skill.name, skill.label)] = body
    return skill


def _active_config(
    langfuse_prompts, *, system_prompt: str = SYSTEM_PROMPT, **fields
) -> CompanionConfig:
    """有効な設定を作り、システムプロンプトの本文を Langfuse の代役に production で置く."""
    langfuse_prompts[(SYSTEM_PROMPT_NAME, "production")] = system_prompt
    return CompanionConfigFactory(
        is_active=True, system_prompt__name=SYSTEM_PROMPT_NAME, **fields
    )


@pytest.fixture
def config(db, langfuse_prompts) -> CompanionConfig:
    """有効な設定と、名前順と逆に選んだスキル 3 件（welcome-home は無効）."""
    skills = [
        _skill(
            langfuse_prompts,
            name,
            body,
            description=description,
            is_enabled=is_enabled,
        )
        for name, description, body, is_enabled in [
            ("welcome-home", "帰宅のあいさつ（「ただいま」など）", HOME_BODY, False),
            ("good-night", "夜のあいさつ（「おやすみ」など）", NIGHT_BODY, True),
            ("good-morning", "朝のあいさつ（「おはよう」など）", MORNING_BODY, True),
        ]
    ]
    return _active_config(langfuse_prompts, area_code=AREA_CODE, skills=skills)


@pytest.fixture
def tts_config(config) -> CompanionConfig:
    """音声合成を有効にした設定（項目は既定値と違う値にする）."""
    config.tts_enabled = True
    config.tts_model = "hiroki"
    config.tts_style = "Happy"
    config.tts_speed = 1.2
    config.tts_format = "mp3"
    config.save()
    return config


def _scripted(*script) -> ScriptedLLM:
    """本番のプロファイルで応答する台本（読み込んだ本文が会話途中の system で届く）."""
    return ScriptedLLM(*script, profile=_LITELLM_PROFILE)


def _run(llm: ScriptedLLM, *, skill: str | None = None) -> CompanionReply:
    """台本のモデルで、発話「おはよう」に答える run_companion を 1 回実行する."""
    with COMPANION_AGENT.override(model=llm.model):
        return run_companion("おはよう", skill=skill)


def _tool_names(request: RecordedRequest) -> set[str]:
    """リクエストでモデルに渡したツールの名前."""
    return {tool.name for tool in request.function_tools}


def _catalog_entries(request: RecordedRequest) -> list[str]:
    """システムプロンプトを含まない system に載った、スキルの一覧の項目行（`- 名前: 説明`）.

    一覧の見出しと `<context>` の囲みは PydanticAI の定型文なので、ここでは見ない。
    """
    return [
        line
        for text in request.system_prompts
        if SYSTEM_PROMPT not in text
        for line in text.splitlines()
        if line.startswith("- ")
    ]


def _logged(
    caplog: pytest.LogCaptureFixture, level: int, logger: str = SERVICES
) -> list[str]:
    """モジュール（既定はサービス）が出した、指定したレベルのログのメッセージを返す."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == logger and record.levelno == level
    ]


class TestAutoSelection:
    """スキルを指定しない実行（モデルが一覧から選んで読み込む）."""

    def test_run_companion_with_matching_skill_returns_text_and_loaded_skill(
        self, config
    ):
        """スキルを読み込み、ツールを使ってから答えると、セリフと読み込んだスキルを返す."""
        llm = _scripted(
            load_capability("good-morning"), tool_call("get_datetime"), "おはよう！"
        )

        reply = _run(llm)

        assert reply == CompanionReply(
            text="おはよう！", skill="good-morning", audio=None
        )
        assert len(llm.requests) == 3

    def test_run_companion_first_system_is_system_prompt_then_policy_with_loading_rule(
        self, config
    ):
        """最初の system はシステムプロンプト、その後ろに読み込みの一文を含む方針."""
        llm = _scripted("こんにちは")

        _run(llm)

        first = llm.requests[0]
        assert first.system_prompts[0] == (
            f"{SYSTEM_PROMPT}\n\n{response_policy(can_load_skills=True)}"
        )
        assert "load_capability" in _tool_names(first)

    def test_run_companion_catalog_lists_only_enabled_skills_in_name_order(
        self, config
    ):
        """一覧（システムプロンプトの後ろの別の system）には、有効なスキルだけが名前順に載る."""
        llm = _scripted("こんにちは")

        _run(llm)

        assert _catalog_entries(llm.requests[0]) == [
            "- good-morning: 朝のあいさつ（「おはよう」など）",
            "- good-night: 夜のあいさつ（「おやすみ」など）",
        ]

    def test_run_companion_passes_area_code_of_config_to_tools(self, config):
        """ツールへ渡す予報区コードは、有効な設定の値."""
        with patch("features.companion.agent.WeatherClient", autospec=True) as cls:
            cls.return_value.get_weather.return_value = {"weather": "晴れ"}

            _run(_scripted(tool_call("get_weather"), "おはよう！"))

        cls.return_value.get_weather.assert_called_once_with(AREA_CODE, 0)

    def test_run_companion_sends_requests_as_companion_service(
        self, config, llm_settings
    ):
        """LLM の接続設定は companion のもので、リクエストのメタデータもそのサービス名."""
        llm = _scripted("こんにちは")

        _run(llm)

        llm_settings.assert_called_once_with("companion")
        metadata = llm.requests[0].model_settings["extra_body"]["metadata"]
        assert metadata["service_name"] == "companion"

    def test_run_companion_without_loading_skill_returns_no_skill(self, config):
        """どのスキルも読み込まずに答えたら、使ったスキルは None."""
        reply = _run(_scripted("こんにちは"))

        assert reply.skill is None

    def test_run_companion_strips_whitespace_around_text(self, config):
        """セリフは前後の空白を除いて返す."""
        reply = _run(_scripted("\n おはよう！ \n"))

        assert reply.text == "おはよう！"

    def test_run_companion_without_enabled_skills_offers_no_skills(
        self, db, langfuse_prompts
    ):
        """有効なスキルがなければ、一覧も読み込みのツールも、方針の読み込みの一文も入れない."""
        _active_config(
            langfuse_prompts,
            skills=[AgentSkillFactory(name="good-morning", is_enabled=False)],
        )
        llm = _scripted("こんにちは")

        reply = _run(llm)

        first = llm.requests[0]
        assert first.system_prompts == [
            f"{SYSTEM_PROMPT}\n\n{response_policy(can_load_skills=False)}"
        ]
        assert "load_capability" not in _tool_names(first)
        assert reply.skill is None

    def test_run_companion_reads_config_and_skills_in_two_queries(
        self, config, django_assert_num_queries
    ):
        """DB は 2 クエリだけ読む（スキルを読み込んで本文を取っても増えない）.

        有効な設定はシステムプロンプトの参照ごと 1 クエリ、設定で選んだ有効なスキルは
        1 クエリ（中間表との結合）。スキルの本文は Langfuse から取るので DB を読まない。
        """
        with django_assert_num_queries(2):
            reply = _run(_scripted(load_capability("good-morning"), "おはよう！"))

        assert reply.skill == "good-morning"

    def test_run_companion_when_loaded_skill_body_unavailable_raises_error_after_one_request(
        self, config, langfuse_prompts
    ):
        """読み込んだスキルの本文を Langfuse から取れなければ、続けずに PromptUnavailableError.

        モデルへのリクエストは読み込みを決めた 1 回だけ（本文のない手順で答えさせない）。
        """
        del langfuse_prompts[("good-morning", "staging")]
        llm = _scripted(load_capability("good-morning"), "おはよう！")

        with pytest.raises(PromptUnavailableError) as exc_info:
            _run(llm)

        assert exc_info.value.ref_name == "good-morning"
        assert len(llm.requests) == 1


class TestSkillSpecified:
    """スキルを指定した実行（一覧も読み込みもなく、本文を指示に足す）."""

    def test_run_companion_with_skill_answers_in_one_request_without_loader(
        self, config
    ):
        """1 回のリクエストで答え、読み込みのツールを出さず、指定したスキルを返す."""
        llm = _scripted("おやすみ！")

        reply = _run(llm, skill="good-night")

        assert reply == CompanionReply(
            text="おやすみ！", skill="good-night", audio=None
        )
        assert len(llm.requests) == 1
        assert "load_capability" not in _tool_names(llm.requests[0])

    def test_run_companion_with_skill_appends_its_body_after_system_prompt_and_policy(
        self, config
    ):
        """system は 1 つだけで、システムプロンプト → 読み込みの一文のない方針 → スキルの本文の順."""
        llm = _scripted("おやすみ！")

        _run(llm, skill="good-night")

        night = config.skills.get(name="good-night")
        assert llm.requests[0].system_prompts == [
            "\n\n".join(
                [
                    SYSTEM_PROMPT,
                    response_policy(can_load_skills=False),
                    skill_instructions(night),
                ]
            )
        ]
        assert llm.requests[0].system_prompts[0].endswith(NIGHT_BODY)

    def test_run_companion_with_skill_and_leaked_tool_call_returns_retried_text(
        self, config
    ):
        """スキルを指定した実行でも、本文に漏れた呼び出しの書式は作り直させる（検証はエージェント全体）."""
        llm = _scripted(LEAKED_TOOL_CALL, "おやすみ！")

        reply = _run(llm, skill="good-night")

        assert reply.text == "おやすみ！"
        assert len(llm.requests) == 2

    @pytest.mark.parametrize("body", EMPTY_TEXTS)
    def test_run_companion_with_skill_with_empty_body_raises_error_before_llm(
        self, config, langfuse_prompts, body
    ):
        """指定したスキルの本文が空なら、モデルを呼ばずに PromptUnavailableError を送出する."""
        config.skills.add(_skill(langfuse_prompts, "good-evening", body))
        llm = _scripted("こんばんは")

        with pytest.raises(PromptUnavailableError) as exc_info:
            _run(llm, skill="good-evening")

        assert exc_info.value.ref_name == "good-evening"
        assert llm.requests == []

    def test_run_companion_with_skill_when_body_unavailable_raises_error_before_llm(
        self, config, langfuse_prompts
    ):
        """指定したスキルの本文を Langfuse から取れなければ、モデルを呼ばずに PromptUnavailableError.

        システムプロンプトは取れても、スキルの本文のプロンプトがそのラベルになければ止まる。
        """
        del langfuse_prompts[("good-night", "staging")]
        llm = _scripted("おやすみ！")

        with pytest.raises(PromptUnavailableError) as exc_info:
            _run(llm, skill="good-night")

        assert exc_info.value.ref_name == "good-night"
        assert llm.requests == []

    def test_run_companion_with_skill_uses_body_for_label_of_skill(
        self, config, langfuse_prompts
    ):
        """本文はスキルのラベルのプロンプトから取る（ほかのラベルの本文は使わない）."""
        night = config.skills.get(name="good-night")
        night.label = "production"
        night.save()
        langfuse_prompts[(night.name, "production")] = "本番の本文"
        llm = _scripted("おやすみ！")

        _run(llm, skill="good-night")

        (system_prompt,) = llm.requests[0].system_prompts
        assert system_prompt.endswith("本番の本文")
        assert NIGHT_BODY not in system_prompt

    @pytest.mark.parametrize(
        "skill",
        ["good-evening", "welcome-home", "unselected-skill", "other-skill"],
        ids=["unregistered", "disabled", "unselected", "other-config"],
    )
    def test_run_companion_with_unavailable_skill_raises_error_before_llm(
        self, config, llm_settings, skill
    ):
        """有効な設定で選んだ有効なスキルでなければ、LLM の設定を読む前に UnknownSkillError.

        登録がない・無効・登録はあるがどの設定でも選んでいない・ほかの設定だけが選んでいる。
        """
        AgentSkillFactory(name="unselected-skill")
        CompanionConfigFactory(skills=[AgentSkillFactory(name="other-skill")])
        llm = _scripted("こんにちは")

        with pytest.raises(UnknownSkillError, match=skill) as exc_info:
            _run(llm, skill=skill)

        assert exc_info.value.skill_name == skill
        assert llm.requests == []
        llm_settings.assert_not_called()


class TestBeforeModelErrors:
    """モデルを呼ぶ前に止まる失敗."""

    @pytest.fixture
    def two_active_configs(self, db) -> None:
        """有効な設定が 2 件ある DB（2 件を同時に有効にしたときに起こりうる）.

        save() はほかの設定を無効にするので、update で 2 件とも有効にする。
        """
        CompanionConfigFactory.create_batch(2)
        CompanionConfig.objects.update(is_active=True)

    def test_run_companion_without_active_config_raises_not_configured_error(
        self, db, llm_settings
    ):
        """有効な設定がなければ CompanionNotConfiguredError（LLM の設定も読まない）."""
        CompanionConfigFactory(is_active=False)
        llm = _scripted("こんにちは")

        with pytest.raises(CompanionNotConfiguredError):
            _run(llm)

        assert llm.requests == []
        llm_settings.assert_not_called()

    def test_run_companion_with_two_active_configs_raises_not_configured_error(
        self, two_active_configs, llm_settings
    ):
        """有効な設定が複数あれば、どれも使わずに CompanionNotConfiguredError（LLM の設定も読まない）."""
        llm = _scripted("こんにちは")

        with pytest.raises(CompanionNotConfiguredError) as exc_info:
            _run(llm)

        assert exc_info.value.multiple is True
        assert llm.requests == []
        llm_settings.assert_not_called()

    def test_run_companion_with_two_active_configs_logs_error_naming_cause(
        self, two_active_configs, caplog
    ):
        """有効な設定が複数あることを error ログに出す（503 の原因を追えるように）."""
        with pytest.raises(CompanionNotConfiguredError):
            _run(_scripted("こんにちは"))

        (message,) = _logged(caplog, logging.ERROR)
        assert "有効な Companion 設定が複数あります" in message

    def test_run_companion_without_llm_settings_propagates_configuration_error(
        self, config, llm_settings
    ):
        """companion の LLM サービス設定がなければ、LLMConfigurationError をそのまま送出する."""
        llm_settings.side_effect = LLMConfigurationError(
            "サービス 'companion' のLLM設定がありません。"
        )
        llm = _scripted("こんにちは")

        with pytest.raises(LLMConfigurationError):
            _run(llm)

        assert llm.requests == []

    @pytest.mark.parametrize("body", EMPTY_TEXTS)
    def test_run_companion_with_empty_system_prompt_raises_prompt_unavailable_error(
        self, db, langfuse_prompts, body
    ):
        """システムプロンプトの本文が空なら、モデルを呼ばずに PromptUnavailableError."""
        _active_config(langfuse_prompts, system_prompt=body)
        llm = _scripted("こんにちは")

        with pytest.raises(PromptUnavailableError) as exc_info:
            _run(llm)

        assert exc_info.value.ref_name == SYSTEM_PROMPT_NAME
        assert llm.requests == []


class TestRunLimits:
    """応答が空のとき・上限と再試行."""

    @pytest.mark.parametrize("output", EMPTY_TEXTS)
    def test_run_companion_with_empty_output_raises_output_error_without_tts(
        self, tts_config, tts_client, output
    ):
        """応答の本文が空（空白だけ）なら LLMOutputError にし、音声合成はしない."""
        with pytest.raises(LLMOutputError):
            _run(_scripted(output))

        tts_client.assert_not_called()

    def test_run_companion_with_leaked_tool_call_twice_raises_output_error_without_tts(
        self, tts_config, tts_client
    ):
        """作り直させても呼び出しの書式が漏れたら、作り直しは 1 回だけで LLMOutputError にし、音声合成はしない."""
        llm = _scripted(LEAKED_TOOL_CALL, LEAKED_TOOL_CALL)

        with pytest.raises(LLMOutputError):
            _run(llm)

        assert len(llm.requests) == 2
        tts_client.assert_not_called()

    def test_run_companion_with_endless_tool_calls_stops_at_request_limit(self, config):
        """ツールを呼び続けると、リクエストの上限で止めて LLMClientError にする."""
        llm = _scripted(*[tool_call("get_datetime")] * (REQUEST_LIMIT + 1))

        with pytest.raises(LLMClientError):
            _run(llm)

        assert len(llm.requests) == REQUEST_LIMIT

    def test_run_companion_with_too_many_tool_calls_stops_before_running_them(
        self, config
    ):
        """1 回の応答でツール呼び出しの上限を超えたら、実行せずに LLMClientError にする."""
        llm = _scripted(
            tool_calls(*["get_weather"] * (TOOL_CALLS_LIMIT + 1)), "おはよう！"
        )

        with (
            patch("features.companion.agent.WeatherClient", autospec=True) as cls,
            pytest.raises(LLMClientError),
        ):
            _run(llm)

        cls.return_value.get_weather.assert_not_called()

    def test_run_companion_exceeding_run_timeout_raises_timeout_error_without_tts(
        self, tts_config, tts_client
    ):
        """実行全体が RUN_TIMEOUT を過ぎたら、そこで止めて LLMTimeoutError にし、音声合成はしない.

        テストを速くするため、RUN_TIMEOUT を短くして確かめる。
        """
        with (
            patch(f"{SERVICES}.RUN_TIMEOUT", 0.05),
            COMPANION_AGENT.override(model=slow_model(1)),
            pytest.raises(LLMTimeoutError),
        ):
            run_companion("おはよう")

        tts_client.assert_not_called()

    def test_run_companion_after_two_failed_skill_loads_uses_later_loaded_skill(
        self, config
    ):
        """読み込みに 2 回続けて失敗しても、その後に読み込めれば答える.

        PydanticAI の既定（再試行 1 回）では実行が失敗する回数（`test_skills.py`）。
        """
        llm = _scripted(
            load_capability("good-evening"),
            load_capability("good-afternoon"),
            load_capability("good-morning"),
            "おはよう！",
        )

        reply = _run(llm)

        assert reply.skill == "good-morning"

    def test_run_companion_with_more_failed_skill_loads_than_retries_raises_error(
        self, config
    ):
        """読み込みに再試行の回数を超えて続けて失敗すると、LLMOutputError で実行が失敗する."""
        failures = [load_capability(f"unknown-{n}") for n in range(TOOL_RETRIES + 1)]

        with pytest.raises(LLMOutputError, match="load_capability"):
            _run(_scripted(*failures, "おはよう！"))


class TestSpeech:
    """音声合成."""

    def test_run_companion_with_tts_enabled_synthesizes_text_with_config_options(
        self, tts_config, tts_client
    ):
        """音声合成が有効なら、セリフを設定の項目どおりに 1 回だけ合成して返す."""
        reply = _run(_scripted("おはよう！"))

        tts_client.assert_called_once_with()
        tts_client.return_value.synthesize.assert_called_once_with(
            "おはよう！", **tts_config.get_tts_options()
        )
        assert reply.audio == AUDIO

    def test_run_companion_with_tts_disabled_returns_no_audio_without_client(
        self, config, tts_client
    ):
        """音声合成が無効なら、クライアントを作らず音声は None."""
        reply = _run(_scripted("おはよう！"))

        assert reply.audio is None
        tts_client.assert_not_called()

    def test_run_companion_with_tts_error_propagates_it(self, tts_config, tts_client):
        """音声合成の失敗はそのまま送出する."""
        tts_client.return_value.synthesize.side_effect = TTSNetworkError(
            "TTSサービスへの接続に失敗しました"
        )

        with pytest.raises(TTSNetworkError):
            _run(_scripted("おはよう！"))


class TestLangfuseOutput:
    """Langfuse のスパン（companion/run）への出力の記録."""

    @pytest.fixture
    def langfuse_client(self):
        """出力を記録する Langfuse のクライアントを差し替える."""
        with patch(f"{SERVICES}.get_client") as get_client:
            yield get_client.return_value

    def test_run_companion_records_only_text_and_skill_as_span_output(
        self, tts_config, langfuse_client
    ):
        """スパンの出力にはセリフと使ったスキルだけを記録し、音声は送らない."""
        reply = _run(_scripted(load_capability("good-morning"), "おはよう！"))

        assert reply.audio == AUDIO
        assert langfuse_client.mock_calls == [
            call.update_current_span(
                output={"text": "おはよう！", "skill": "good-morning"}
            )
        ]

    def test_run_companion_when_tts_fails_still_records_output(
        self, tts_config, tts_client, langfuse_client
    ):
        """出力は音声合成の前に記録するので、音声合成に失敗してもセリフは残る."""
        tts_client.return_value.synthesize.side_effect = TTSNetworkError(
            "TTSサービスへの接続に失敗しました"
        )

        with pytest.raises(TTSNetworkError):
            _run(_scripted("おはよう！"))

        langfuse_client.update_current_span.assert_called_once_with(
            output={"text": "おはよう！", "skill": None}
        )

    def test_run_companion_when_recording_output_fails_only_warns(
        self, config, langfuse_client, caplog
    ):
        """記録に失敗しても warning を出すだけで、セリフを返す."""
        langfuse_client.update_current_span.side_effect = RuntimeError(
            "Langfuse に送れません"
        )

        reply = _run(_scripted("おはよう！"))

        assert reply.text == "おはよう！"
        (message,) = _logged(caplog, logging.WARNING)
        assert "Langfuse に送れません" in message


class TestLangfuseSession:
    """Langfuse のセッション（その日の実行を 1 つのセッションにまとめる）."""

    @pytest.fixture
    def propagate_attributes(self):
        """Langfuse の属性の伝播（`langfuse.propagate_attributes`）を差し替える."""
        with patch("langfuse.propagate_attributes") as mocked:
            yield mocked

    @pytest.fixture
    def after_midnight_in_japan(self):
        """Django の現在時刻を 2026-11-07 15:30 UTC（日本時間では 11-08 の 00:30）に固定する."""
        with patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 11, 7, 15, 30, tzinfo=UTC),
        ):
            yield

    def test_run_companion_runs_in_session_of_date_in_japan(
        self, config, propagate_attributes, after_midnight_in_japan
    ):
        """実行は companion/<日本時間の日付> のセッションの中で行う（UTC ではまだ前日でも）."""
        reply = _run(_scripted("おはよう！"))

        assert reply.text == "おはよう！"
        propagate_attributes.assert_called_once_with(session_id="companion/2026-11-08")
        propagate_attributes.return_value.__enter__.assert_called_once_with()
        propagate_attributes.return_value.__exit__.assert_called_once()

    def test_run_companion_stopped_before_model_still_runs_in_session(
        self, db, propagate_attributes, after_midnight_in_japan
    ):
        """モデルを呼ぶ前に止まった実行も同じセッションに入れ、伝播は解除する."""
        with pytest.raises(CompanionNotConfiguredError):
            _run(_scripted("こんにちは"))

        propagate_attributes.assert_called_once_with(session_id="companion/2026-11-08")
        propagate_attributes.return_value.__exit__.assert_called_once()

    def test_run_companion_when_session_propagation_fails_only_warns(
        self, config, propagate_attributes, caplog
    ):
        """セッションを付けられなくても warning を出すだけで、セリフを返す.

        同じロガーには、システムプロンプトのフォールバックの warning も出る。
        """
        propagate_attributes.return_value.__enter__.side_effect = RuntimeError(
            "Langfuse に送れません"
        )

        reply = _run(_scripted("おはよう！"))

        assert reply.text == "おはよう！"
        assert "Langfuse session_id 設定失敗: Langfuse に送れません" in _logged(
            caplog, logging.WARNING, logger=LANGFUSE_CLIENT
        )
