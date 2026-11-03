"""Companion の実行サービス.

有効な設定・スキル・キャラクター設定から実行の指示を組み立て、COMPANION_AGENT を 1 回
実行してセリフを返す（音声合成が有効なら音声も）。流れと各段階で送出する例外は
`README.md` の「実行の流れ」。
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from langfuse import get_client, observe
from pydantic_ai.capabilities import Capability
from pydantic_ai.usage import UsageLimits

from integrations.llm.config import get_llm_settings
from integrations.llm.exceptions import LLMOutputError
from integrations.llm.runtime import run_agent_sync
from integrations.tts.client import TTSClient, TTSResult

from .agent import COMPANION_AGENT, CompanionDeps, response_policy
from .exceptions import CompanionNotConfiguredError, UnknownSkillError
from .models import CompanionConfig, CompanionSkill
from .skills import (
    build_skill_capabilities,
    loaded_skill,
    resolve_required_prompt,
    skill_instructions,
)

logger = logging.getLogger(__name__)

# 1 回の実行でモデルへ送るリクエストの上限（スキルの読み込み・ツールの往復・最後の応答を含む）
REQUEST_LIMIT = 6
# 1 回の実行で動かすツール呼び出しの上限（load_capability を含む）
TOOL_CALLS_LIMIT = 8
# ツールごとに続けて失敗してよい回数（不明なスキル名の load_capability・引数の誤りなど）。
# PydanticAI の既定（1 回）では、読み込みに 2 回続けて失敗しただけで実行が失敗する
TOOL_RETRIES = 3
# 1 回の実行（モデルへのリクエストとツールの実行をすべて含む）の制限時間（秒）。
# リクエストごとのタイムアウト（LLM サービス設定）だけでは、合計が REQUEST_LIMIT 回分まで延びる。
# 本番の nginx は応答を 120 秒までしか待たない（frontend/nginx.conf の proxy_read_timeout）ので、
# 音声合成の時間を残す
RUN_TIMEOUT = 60


@dataclass(frozen=True)
class CompanionReply:
    """Companion の実行結果.

    Attributes:
        text: セリフ（前後の空白を除いたもの。空にはならない）
        skill: 使ったスキルの名前（指定したスキルか、最初に読み込んだスキル。なければ None）
        audio: 音声（音声合成が無効なら None）
    """

    text: str
    skill: str | None
    audio: TTSResult | None


@observe(name="companion/run", capture_output=False)
def run_companion(prompt: str, skill: str | None = None) -> CompanionReply:
    """発話に答えるセリフを生成する（音声合成が有効なら音声も）.

    設定・スキル・LLM の接続設定・キャラクター設定の確認で止まったときは、モデルを呼ばない。
    Langfuse のスパンの出力には、セリフと使ったスキルだけを記録する（音声は送らない）。

    Args:
        prompt: 発話（例: 「おはよう」）
        skill: 使うスキルの名前。指定するとモデルに選ばせず、一覧も読み込みも使わない

    Returns:
        セリフ・使ったスキル・音声

    Raises:
        CompanionNotConfiguredError: 有効な設定がないか、複数ある場合
        UnknownSkillError: 指定したスキルが有効な設定にないか、無効な場合
        LLMConfigurationError: companion の LLM サービス設定がない場合
        PromptUnavailableError: キャラクター設定か、使うスキルの本文が空の場合
        LLMOutputError: 応答の本文が空の場合・読み込みなどのツールの失敗が続いた場合
        LLMTimeoutError: リクエストごとのタイムアウトか、実行全体の RUN_TIMEOUT を過ぎた場合
        LLMClientError: そのほか LLM の実行に失敗した場合（上限の超過を含む）
        TTSError: 音声合成に失敗した場合
    """
    config = _active_config()
    skills = list(config.skills.filter(is_enabled=True).select_related("prompt_ref"))
    selected = None if skill is None else _find_skill(skills, skill)
    settings = get_llm_settings("companion")
    persona = resolve_required_prompt(config.persona_prompt_ref)
    instructions, capabilities = _instructions_and_capabilities(
        persona, skills, selected
    )

    result = run_agent_sync(
        COMPANION_AGENT,
        settings,
        user_prompt=prompt,
        instructions=instructions,
        deps=CompanionDeps(area_code=config.area_code),
        capabilities=capabilities,
        usage_limits=UsageLimits(
            request_limit=REQUEST_LIMIT, tool_calls_limit=TOOL_CALLS_LIMIT
        ),
        retries={"tools": TOOL_RETRIES},
        run_timeout=RUN_TIMEOUT,
    )
    text = (result.output or "").strip()
    if not text:
        raise LLMOutputError("LLMの応答に本文がありませんでした")
    used_skill = (
        selected.name if selected is not None else loaded_skill(result.all_messages())
    )
    logger.info("Companion の応答を生成: skill=%s %d文字", used_skill, len(text))

    _record_output(text, used_skill)
    audio = _synthesize(config, text)
    return CompanionReply(text=text, skill=used_skill, audio=audio)


def _active_config() -> CompanionConfig:
    """有効な設定を返す（キャラクター設定の参照ごと）.

    有効な設定が複数ある（2 件を同時に有効にすると起こりうる）ときは、どれかを選ばずに
    設定の不備として止め、原因を error ログに出す。
    """
    try:
        return CompanionConfig.objects.get_active_config()
    except CompanionConfig.DoesNotExist as exc:
        raise CompanionNotConfiguredError() from exc
    except CompanionConfig.MultipleObjectsReturned as exc:
        error = CompanionNotConfiguredError(multiple=True)
        logger.error("%s", error)
        raise error from exc


def _find_skill(skills: Sequence[CompanionSkill], name: str) -> CompanionSkill:
    """有効なスキルの中から、指定された名前のスキルを返す."""
    for candidate in skills:
        if candidate.name == name:
            return candidate
    raise UnknownSkillError(name)


def _instructions_and_capabilities(
    persona: str, skills: Sequence[CompanionSkill], selected: CompanionSkill | None
) -> tuple[str, list[Capability[CompanionDeps]]]:
    """実行の指示と、実行に渡す capability を決める.

    指示はキャラクター設定 → 方針の順。スキルを指定したときは、その本文の節
    （`skill_instructions`）を末尾に足し、capability は渡さない。指定しないときは有効な
    スキルを一覧（遅延 capability）にし、スキルがあるときだけ方針に読み込みの一文を入れる。
    """
    if selected is not None:
        sections = (
            persona,
            response_policy(can_load_skills=False),
            skill_instructions(selected),
        )
        return "\n\n".join(sections), []
    sections = (persona, response_policy(can_load_skills=bool(skills)))
    return "\n\n".join(sections), build_skill_capabilities(skills)


def _record_output(text: str, skill: str | None) -> None:
    """現在の Langfuse のスパン（companion/run）の出力に、セリフと使ったスキルを記録する.

    戻り値には音声（バイト列）が入るので自動では記録させず、ここで記録する。音声合成の前に
    記録するので、音声合成に失敗してもセリフは残る。記録に失敗しても実行は続ける。
    """
    try:
        get_client().update_current_span(output={"text": text, "skill": skill})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse に Companion の出力を記録できませんでした: %s", exc)


def _synthesize(config: CompanionConfig, text: str) -> TTSResult | None:
    """音声合成が有効なら、セリフを設定の項目どおりに音声にする（失敗はそのまま送出する）."""
    options = config.get_tts_options()
    if options is None:
        return None
    return TTSClient().synthesize(text, **options)
