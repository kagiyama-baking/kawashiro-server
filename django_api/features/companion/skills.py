"""スキル（AgentSkill）を、実行ごとの遅延 capability にする.

PydanticAI の on-demand capability を使う。モデルにはスキル名と説明の一覧（カタログ）だけを
見せ、モデルが組み込みの `load_capability` ツールで読み込んだスキルの本文だけを、その後の
リクエストに system として入れる。本文は読み込まれたときに、スキル名と同じ名前の Langfuse の
text プロンプトをスキルのラベルで取り（`integrations.llm.skills.resolve_skill_body`。
フォールバックはない）、1 回の実行で 1 回だけ取る。

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

from integrations.llm.models import AgentSkill
from integrations.llm.skills import resolve_skill_body

from .agent import CompanionDeps

# スキルを指定した実行で、本文の前に置く見出し
_SKILL_SECTION_HEADING = "# 今回の手順"


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
