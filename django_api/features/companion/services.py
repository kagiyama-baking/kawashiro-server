"""Companion の実行サービス.

有効な設定・スキル・システムプロンプトから実行の指示を組み立て、COMPANION_AGENT を 1 回
実行してセリフを返す（音声合成が有効なら音声も）。流れと各段階で送出する例外は
`README.md` の「実行の流れ」。
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from django.utils import timezone
from langfuse import get_client, observe
from pydantic_ai.capabilities import Capability
from pydantic_ai.usage import UsageLimits

from integrations.langfuse.client import langfuse_session, resolve_required_prompt
from integrations.llm.config import get_llm_settings
from integrations.llm.exceptions import LLMOutputError
from integrations.llm.models import AgentSkill
from integrations.llm.runtime import run_agent_sync
from integrations.tts.client import TTSClient, TTSResult

from .agent import COMPANION_AGENT, CompanionDeps, response_policy
from .exceptions import CompanionNotConfiguredError, UnknownSkillError
from .models import CompanionConfig
from .skills import (
    build_skill_capabilities,
    loaded_skill,
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

    設定・スキル・LLM の接続設定・システムプロンプトの確認で止まったときは、モデルを呼ばない。
    Langfuse のスパンの出力には、セリフと使ったスキルだけを記録する（音声は送らない）。
    実行は、止まったときも含めて、その日の Langfuse のセッション（`companion/<日本時間の日付>`）
    に入れる。

    Args:
        prompt: 発話（例: 「おはよう」）
        skill: 使うスキルの名前（有効な設定で選んだ有効なスキル）。指定するとモデルに
            選ばせず、一覧も読み込みも使わない

    Returns:
        セリフ・使ったスキル・音声

    Raises:
        CompanionNotConfiguredError: 有効な設定がないか、複数ある場合
        UnknownSkillError: 指定したスキルが、有効な設定で選ばれていないか、無効な場合
        LLMConfigurationError: companion の LLM サービス設定がない場合
        PromptUnavailableError: システムプロンプトの本文が空の場合か、使うスキルの本文を
            Langfuse から取れないか、空の場合
        LLMOutputError: 応答の本文が空の場合・読み込みなどのツールの失敗が続いた場合・
            本文に漏れたツール呼び出しの書式が作り直させても直らなかった場合
        LLMTimeoutError: リクエストごとのタイムアウトか、実行全体の RUN_TIMEOUT を過ぎた場合
        LLMClientError: そのほか LLM の実行に失敗した場合（上限の超過を含む）
        TTSError: 音声合成に失敗した場合
    """
    with langfuse_session(_session_id()):
        return _run_companion(prompt, skill)


def _session_id() -> str:
    """その日の実行をまとめる Langfuse のセッション ID（`companion/<日本時間の日付>`）を返す.

    朝・夜の自動化など 1 日の実行が、Langfuse の Sessions で 1 つにまとまる。日付は
    Django の TIME_ZONE（Asia/Tokyo）で決める。
    """
    return f"companion/{timezone.localdate().isoformat()}"


def _run_companion(prompt: str, skill: str | None) -> CompanionReply:
    """run_companion の本体（その日の Langfuse のセッションの中で実行する）."""
    config = _active_config()
    skills = list(config.skills.filter(is_enabled=True))
    selected = None if skill is None else _find_skill(skills, skill)
    settings = get_llm_settings("companion")
    system_prompt = resolve_required_prompt(config.system_prompt)
    instructions, capabilities = _instructions_and_capabilities(
        system_prompt, skills, selected
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
        # ツールの回数だけを変える。出力の検証（agent.py）で作り直させるのは既定の 1 回のまま
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
    """有効な設定を返す（システムプロンプトの参照ごと）.

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


def _find_skill(skills: Sequence[AgentSkill], name: str) -> AgentSkill:
    """有効な設定で選んだ有効なスキルの中から、指定された名前のスキルを返す."""
    for candidate in skills:
        if candidate.name == name:
            return candidate
    raise UnknownSkillError(name)


def _instructions_and_capabilities(
    system_prompt: str,
    skills: Sequence[AgentSkill],
    selected: AgentSkill | None,
) -> tuple[str, list[Capability[CompanionDeps]]]:
    """実行の指示と、実行に渡す capability を決める.

    指示はシステムプロンプト → 方針の順。スキルを指定したときは、その本文の節
    （`skill_instructions`。ここで本文を Langfuse から取る）を末尾に足し、capability は
    渡さない。指定しないときは設定で選んだ有効なスキルを一覧（遅延 capability）にし、
    スキルがあるときだけ方針に読み込みの一文を入れる。
    """
    if selected is not None:
        sections = (
            system_prompt,
            response_policy(can_load_skills=False),
            skill_instructions(selected),
        )
        return "\n\n".join(sections), []
    sections = (system_prompt, response_policy(can_load_skills=bool(skills)))
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
