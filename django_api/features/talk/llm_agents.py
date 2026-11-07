"""Talk の LLM エージェント定義.

実行時に渡すモデルとシステムプロンプト以外の状態を持たないので、モジュールで共有する。
出力に `None` を許し、本文のない応答を再試行せず空として受ける（呼び出し側で空文字にする）。
"""

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

# ストリーミングの実行には instructions の引数がないので、system プロンプトは deps で渡す
TALK_CHAT_AGENT: Agent[str, str | None] = Agent(
    name="talk-chat", deps_type=str, output_type=str | None
)
TALK_TITLE_AGENT: Agent[None, str | None] = Agent(
    name="talk-title", output_type=str | None
)


@TALK_CHAT_AGENT.instructions
def _chat_system_prompt(ctx: RunContext[str]) -> str:
    """`deps` で渡された system プロンプトをそのまま使う."""
    return ctx.deps


def _to_model_message(message: dict[str, str]) -> ModelMessage:
    """`{"role", "content"}` の 1 発言を PydanticAI のメッセージへ変換する."""
    if message["role"] == "assistant":
        return ModelResponse(parts=[TextPart(content=message["content"])])
    return ModelRequest(parts=[UserPromptPart(content=message["content"])])


def split_conversation(
    messages: list[dict[str, str]],
) -> tuple[list[ModelMessage], str]:
    """会話履歴を、過去の履歴と今回のユーザーメッセージに分ける.

    Args:
        messages: `[{"role": "user"|"assistant", "content": ...}]`。末尾は user

    Returns:
        (過去の履歴, 今回のユーザーメッセージの本文)
    """
    *history, latest = messages
    return [_to_model_message(message) for message in history], latest["content"]
