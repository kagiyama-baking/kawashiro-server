"""スキル（CompanionSkill）を、実行ごとの遅延 capability にする.

PydanticAI の on-demand capability を使う。モデルにはスキル名と説明の一覧（カタログ）だけを
見せ、モデルが組み込みの `load_capability` ツールで読み込んだスキルの本文だけを、その後の
リクエストに system として入れる。本文は読み込まれたときに Langfuse から取り、1 回の実行で
1 回だけ解決する。

スキルを指定した実行では capability を使わず、本文を実行の指示の末尾に足す
（`skill_instructions`）。
"""

from collections.abc import Sequence

from asgiref.sync import sync_to_async
from pydantic_ai.capabilities import Capability
from pydantic_ai.messages import (
    LoadCapabilityCallPart,
    LoadCapabilityReturnPart,
    ModelMessage,
)

from integrations.langfuse.client import resolve_prompt
from integrations.langfuse.models import LangfusePromptRef

from .agent import CompanionDeps
from .exceptions import PromptUnavailableError
from .models import CompanionSkill

# スキルを指定した実行で、本文の前に置く見出し
_SKILL_SECTION_HEADING = "# 今回の手順"


def resolve_required_prompt(ref: LangfusePromptRef) -> str:
    """プロンプトの本文を解決し、空なら例外にする.

    `resolve_prompt` は Langfuse から取れなくても例外を出さずにフォールバックテキストへ落ち、
    フォールバックテキストは空でもよい。空のまま「読めた体」で続けないよう、ここで止める。
    Langfuse と通信する同期関数なので、イベントループの外か `sync_to_async` で呼ぶ。

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


def skill_instructions(skill: CompanionSkill) -> str:
    """指定したスキルの本文を解決し、実行の指示の末尾に足す節にする.

    遅延しない capability の指示は実行の指示（キャラクター設定）より前に置かれるので、
    スキルを指定した実行では capability にせず、この節をキャラクター設定・方針の後ろに足す。
    Langfuse と通信する同期関数なので、イベントループの外で呼ぶ。

    Args:
        skill: 指定したスキル

    Returns:
        見出しと本文

    Raises:
        PromptUnavailableError: 本文が空（空白だけ）の場合
    """
    return f"{_SKILL_SECTION_HEADING}\n\n{resolve_required_prompt(skill.prompt_ref)}"


def build_skill_capabilities(
    skills: Sequence[CompanionSkill],
) -> list[Capability[CompanionDeps]]:
    """スキルを、モデルが読み込むまで本文を送らない capability にする（並びはそのまま）.

    本文は capability ごとに覚えるので、実行ごとに組み立てて渡す（使い回すと前の実行で
    解決した本文のままになる）。各スキルの `prompt_ref` はここで読む（サービスは
    `select_related` で先読みしておく）。

    Args:
        skills: 使うスキル（有効なものだけを、カタログに載せたい順で渡す）

    Returns:
        スキルごとの capability（id はスキル名、カタログの説明はスキルの説明）
    """
    return [_skill_capability(skill) for skill in skills]


def _skill_capability(skill: CompanionSkill) -> Capability[CompanionDeps]:
    """1 つのスキルを遅延 capability にする."""
    ref = skill.prompt_ref
    body: str | None = None

    async def instructions() -> str:
        # 読み込まれるまでは呼ばれず、読み込まれた後はリクエストのたびに呼ばれるので、
        # 解決は最初の 1 回だけにする。同期の関数は PydanticAI が別スレッドで動かすので、
        # async にして `sync_to_async` で呼び出し元のスレッド（と DB 接続）に戻して解決する
        nonlocal body
        if body is None:
            body = await sync_to_async(resolve_required_prompt)(ref)
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
