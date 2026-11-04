"""スキル（AgentSkill）を、実行ごとの遅延 capability にする.

PydanticAI の on-demand capability を使う。モデルにはスキル名と説明の一覧（カタログ）だけを
見せ、モデルが組み込みの `load_capability` ツールで読み込んだスキルの本文だけを、その後の
リクエストに system として入れる。本文は読み込まれたときに Langfuse の text プロンプト
`companion-skill-<スキル名>` をスキルのラベルで取り（`resolve_skill_body`。フォールバックは
ない）、1 回の実行で 1 回だけ取る。

スキルを指定した実行では capability を使わず、本文を実行の指示の末尾に足す
（`skill_instructions`）。システムプロンプトは参照（`LangfusePromptRef`）から解決する
（`resolve_required_prompt`）。
"""

from collections.abc import Sequence

from asgiref.sync import sync_to_async
from pydantic_ai.capabilities import Capability
from pydantic_ai.messages import (
    LoadCapabilityCallPart,
    LoadCapabilityReturnPart,
    ModelMessage,
)

from integrations.langfuse.client import fetch_text_prompt, resolve_prompt
from integrations.langfuse.exceptions import LangfusePromptError
from integrations.langfuse.models import LangfusePromptRef

from .agent import CompanionDeps
from .exceptions import PromptUnavailableError
from .models import AgentSkill

# スキルを指定した実行で、本文の前に置く見出し
_SKILL_SECTION_HEADING = "# 今回の手順"


def resolve_required_prompt(ref: LangfusePromptRef) -> str:
    """プロンプト（システムプロンプト）の本文を参照から解決し、空なら例外にする.

    `resolve_prompt` は Langfuse から取れなくても例外を出さずにフォールバックテキストへ落ち、
    フォールバックテキストは空でもよい。空のまま「読めた体」で続けないよう、ここで止める。
    Langfuse と通信する同期関数なので、イベントループの外で呼ぶ。

    Args:
        ref: プロンプトの参照（変数のない text プロンプト）

    Returns:
        前後の空白を除いた本文

    Raises:
        PromptUnavailableError: 本文が空（空白だけ）の場合
    """
    text = resolve_prompt(ref).strip()
    if not text:
        raise PromptUnavailableError(ref.name)
    return text


def resolve_skill_body(skill: AgentSkill) -> str:
    """スキルの本文を Langfuse から取り、取れないか空なら例外にする.

    Langfuse の text プロンプト `companion-skill-<スキル名>`（`skill.prompt_name`）を
    スキルのラベルで取る。フォールバックはない（同じ名前の `LangfusePromptRef` があっても
    使わない）。SDK のキャッシュ（既定 60 秒。取り直しに失敗したら期限切れの本文を返す）は
    そのまま使う。Langfuse と通信する同期関数なので、イベントループの外で呼ぶ。

    Args:
        skill: 本文を取るスキル

    Returns:
        前後の空白を除いた本文

    Raises:
        PromptUnavailableError: 取れない場合（元の LangfusePromptError を `__cause__` に
            持つ）か、本文が空（空白だけ）の場合
    """
    try:
        text = fetch_text_prompt(skill.prompt_name, label=skill.label)
    except LangfusePromptError as exc:
        raise PromptUnavailableError(skill.prompt_name, reason=str(exc)) from exc
    text = text.strip()
    if not text:
        raise PromptUnavailableError(skill.prompt_name, reason="本文が空です")
    return text


def skill_instructions(skill: AgentSkill) -> str:
    """指定したスキルの本文を取り、実行の指示の末尾に足す節にする.

    遅延しない capability の指示は実行の指示（システムプロンプト）より前に置かれるので、
    スキルを指定した実行では capability にせず、この節をシステムプロンプト・方針の後ろに足す。
    Langfuse と通信する同期関数なので、イベントループの外で呼ぶ。

    Args:
        skill: 指定したスキル

    Returns:
        見出しと本文

    Raises:
        PromptUnavailableError: 本文を取れないか、空（空白だけ）の場合
    """
    return f"{_SKILL_SECTION_HEADING}\n\n{resolve_skill_body(skill)}"


def build_skill_capabilities(
    skills: Sequence[AgentSkill],
) -> list[Capability[CompanionDeps]]:
    """スキルを、モデルが読み込むまで本文を送らない capability にする（並びはそのまま）.

    本文は capability ごとに覚えるので、実行ごとに組み立てて渡す（使い回すと前の実行で
    取った本文のままになる）。

    Args:
        skills: 使うスキル（有効なものだけを、カタログに載せたい順で渡す）

    Returns:
        スキルごとの capability（id はスキル名、カタログの説明はスキルの説明）
    """
    return [_skill_capability(skill) for skill in skills]


def _skill_capability(skill: AgentSkill) -> Capability[CompanionDeps]:
    """1 つのスキルを遅延 capability にする."""
    body: str | None = None

    async def instructions() -> str:
        # 読み込まれるまでは呼ばれず、読み込まれた後はリクエストのたびに呼ばれるので、
        # 取るのは最初の 1 回だけにする。同期の関数は PydanticAI が別スレッドで動かすので、
        # async にして `sync_to_async` で呼び出し元のスレッド（システムプロンプトを解決した
        # スレッド）に戻して取る
        nonlocal body
        if body is None:
            body = await sync_to_async(resolve_skill_body)(skill)
        return body

    return Capability(
        id=skill.name,
        description=skill.description,
        instructions=instructions,
        defer_loading=True,
    )


def loaded_skill(messages: Sequence[ModelMessage]) -> str | None:
    """最初に読み込みに成功したスキルの名前を返す（なければ None）.

    モデルの `load_capability` の呼び出しは `LoadCapabilityCallPart` になり、成功した戻り値だけが
    `LoadCapabilityReturnPart` になる（不明な名前・読み込み済みなどの失敗は、再試行を求める
    普通の `ToolReturnPart`）。呼び出しと成功した戻り値を `tool_call_id` で突き合わせる。

    Args:
        messages: 実行の履歴（`AgentRunResult.all_messages()` など）

    Returns:
        スキル名（capability の id）
    """
    parts = [part for message in messages for part in message.parts]
    requested = {
        part.tool_call_id: part.capability_id
        for part in parts
        if isinstance(part, LoadCapabilityCallPart)
    }
    return next(
        (
            capability_id
            for part in parts
            if isinstance(part, LoadCapabilityReturnPart)
            and (capability_id := requested.get(part.tool_call_id)) is not None
        ),
        None,
    )
