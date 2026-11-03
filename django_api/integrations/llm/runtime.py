"""PydanticAI の実行基盤.

LiteLLM Proxy 経由のモデル生成、同期コードからの実行、例外の変換をまとめる。
エージェントの定義は各機能に置き、実行はここの関数だけを通す。
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
from typing import Any

from asgiref.sync import async_to_sync
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from pydantic_ai import Agent, AgentRunResult, RunContext
from pydantic_ai.agent import AgentRetries
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import (
    AgentRunError,
    ModelRequestTimeout,
    ModelTimeoutError,
    RunCancelled,
    RunTimedOut,
    UnexpectedModelBehavior,
)
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIChatModelSettings,
    OpenAIStreamedResponse,
)
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.usage import RequestUsage, UsageLimits

from .config import LLMSettings
from .exceptions import LLMClientError, LLMOutputError, LLMTimeoutError

logger = logging.getLogger(__name__)

# ストリーミングの増分をまとめる幅（秒）。トークンごとに書き込まず、体感を損なわない範囲に抑える
_STREAM_DEBOUNCE_SECONDS = 0.05

# LiteLLM のモデル名は DB 上の任意の文字列なので、名前から推定される既定プロファイルに
# 送受信を左右させない。ここで指定した項目は、どのエイリアスでも同じになる。
_LITELLM_PROFILE = OpenAIModelProfile(
    # max_completion_tokens は LiteLLM の drop_params で黙って落ちることがある
    openai_chat_supports_max_completion_tokens=False,
    # PromptedOutput に response_format を付けない（プロンプト側で JSON を指示している）
    supports_json_object_output=False,
    # system プロンプトの後ろに <system> タグの説明文を足させず、入力の書き換えも止める
    supports_inline_system_prompts=True,
    # system プロンプトを user ロールへ変えない（o1-mini などの名前で切り替わる）
    openai_system_prompt_role="system",
    # tools に strict を付けない（プロバイダーによって解釈が異なる）
    openai_supports_strict_tool_definition=False,
    # reasoning_content などの推論テキストを次のリクエストへ送り返さない
    openai_chat_send_back_thinking_parts=False,
    # 本文中の <think> などを思考として切り取らせない（本文に現れない文字列を指定する）
    thinking_tags=("\x00think\x00", "\x00/think\x00"),
)

_MISSING_API_KEY = "no-api-key-configured"


class _TreatEmptyResponseAsFinished(AbstractCapability[Any]):
    """出力上限やフィルターで本文がなくなった応答を、本文なしの通常の応答として扱う.

    PydanticAI はこれらを例外にするが、呼び出し側は本文なしを空の応答として処理する
    （出力に `None` を許すエージェントは再試行もしない）。
    """

    async def after_model_request(
        self,
        ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        response: ModelResponse,
    ) -> ModelResponse:
        """本文もツール呼び出しもない応答の終了理由を通常の終了にする."""
        if (
            response.finish_reason in ("length", "content_filter")
            and not response.text
            and not response.tool_calls
        ):
            return replace(response, finish_reason="stop")
        return response


def _without_breakdown(usage: RequestUsage) -> RequestUsage:
    """usage から内訳を除く.

    LiteLLM の `text_tokens` や `reasoning_tokens` は output の内数だが、Langfuse は usage の
    全項目を足して total にするので、残すと output を二重に数える。
    """
    return replace(usage, details={})


class _LiteLLMStreamedResponse(OpenAIStreamedResponse):
    """usage の内訳を持たない、LiteLLM のストリーミング応答."""

    def _map_usage(self, response: ChatCompletionChunk) -> RequestUsage:
        return _without_breakdown(super()._map_usage(response))


class _LiteLLMChatModel(OpenAIChatModel):
    """usage の内訳を持たない、LiteLLM の Chat モデル.

    計装はプロバイダーとの境界の usage を読むので、capability の `after_model_request` で
    書き換えても generation には反映されない。応答を作るところで除く。
    """

    def _map_usage(self, response: ChatCompletion) -> RequestUsage:
        return _without_breakdown(super()._map_usage(response))

    @property
    def _streamed_response_cls(self) -> type[OpenAIStreamedResponse]:
        return _LiteLLMStreamedResponse


@contextmanager
def translate_llm_errors() -> Iterator[None]:
    """PydanticAI の例外をプロジェクトの例外へ変換する.

    `RunCancelled` はアプリ自身が止めた結果なので、`UserError` は実装ミスなので変換しない。
    `str(exc)` は応答本文を含むことがあるので、メッセージには `exc.message` を使う。

    Raises:
        LLMTimeoutError: タイムアウト時
        LLMOutputError: 応答が期待する形にならなかった時
        LLMClientError: その他の LLM 実行エラー時（接続エラー・HTTP エラーなど）
    """
    try:
        yield
    except (ModelTimeoutError, ModelRequestTimeout, RunTimedOut) as exc:
        raise LLMTimeoutError("LLM APIへのリクエストがタイムアウトしました") from exc
    except RunCancelled:
        raise
    except UnexpectedModelBehavior as exc:
        raise LLMOutputError(f"LLMの応答を解釈できませんでした: {exc.message}") from exc
    except AgentRunError as exc:
        raise LLMClientError(f"LLM APIの呼び出しに失敗しました: {exc.message}") from exc


def _build_client(settings: LLMSettings) -> AsyncOpenAI:
    """LiteLLM Proxy へ接続するクライアントを作る（接続は最初のリクエストで開く）."""
    return AsyncOpenAI(
        base_url=settings.proxy_base_url,
        # キー未設定でも送信し、認証の判断は LiteLLM に任せる（SDK は空文字を拒否する）
        api_key=settings.proxy_api_key or _MISSING_API_KEY,
        timeout=settings.timeout,
    )


def _build_model(settings: LLMSettings, client: AsyncOpenAI) -> _LiteLLMChatModel:
    """クライアントを使うモデルを作る."""
    return _LiteLLMChatModel(
        settings.model_alias,
        provider=LiteLLMProvider(openai_client=client),
        profile=_LITELLM_PROFILE,
    )


@asynccontextmanager
async def open_model(settings: LLMSettings) -> AsyncIterator[_LiteLLMChatModel]:
    """LiteLLM Proxy へ接続するモデルを開く.

    AsyncOpenAI の接続はイベントループに属し、同期コードからの実行では毎回ループが
    変わるので、クライアントは実行ごとに作って閉じる。
    """
    async with _build_client(settings) as client:
        yield _build_model(settings, client)


def _build_model_settings(
    settings: LLMSettings, *, max_tokens: int | None, reasoning_effort: str | None
) -> OpenAIChatModelSettings:
    """LiteLLM へ送るリクエストパラメータを組み立てる.

    推論深度は `reasoning_effort` として送る。空文字（admin の「無効」）は送らない。
    """
    optional: dict[str, Any] = {}
    if max_tokens is not None:
        optional["max_tokens"] = max_tokens
    if reasoning_effort:
        optional["openai_reasoning_effort"] = reasoning_effort
    return OpenAIChatModelSettings(
        extra_body={
            "metadata": {
                "service_name": settings.service_name,
                "environment": settings.environment,
            }
        },
        **optional,
    )


def _run_options(
    settings: LLMSettings,
    *,
    max_tokens: int | None,
    conversation_id: str | None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """通常の実行とストリーミングの実行で揃える引数を組み立てる."""
    return {
        "model_settings": _build_model_settings(
            settings, max_tokens=max_tokens, reasoning_effort=reasoning_effort
        ),
        "conversation_id": conversation_id or settings.service_name,
        "capabilities": [_TreatEmptyResponseAsFinished()],
    }


async def arun_agent(
    agent: Agent[Any, Any],
    settings: LLMSettings,
    *,
    user_prompt: str,
    instructions: str | None = None,
    message_history: Sequence[ModelMessage] | None = None,
    deps: Any = None,
    usage_limits: UsageLimits | None = None,
    max_tokens: int | None = None,
    retries: int | AgentRetries | None = None,
    conversation_id: str | None = None,
    reasoning_effort: str | None = None,
) -> AgentRunResult[Any]:
    """エージェントを LiteLLM Proxy 経由で 1 回実行する.

    `settings` は DB を読むので、同期の呼び出し側で `get_llm_settings` で解決して渡す。

    Args:
        agent: 実行するエージェント
        settings: 接続設定
        user_prompt: 今回のユーザーメッセージ
        instructions: システムプロンプト
        message_history: 過去の会話履歴
        deps: ツールへ渡す依存
        usage_limits: リクエスト数・ツール呼び出し数の上限
        max_tokens: 出力トークン数の上限
        retries: リトライ回数の上書き
        conversation_id: 会話 ID。Langfuse はこれをセッションとして扱う（`session.id` を
            伝播していればそちらを優先する）。PydanticAI の既定は実行ごとの UUID で、
            セッションが増え続けるので、省略時はサービス名にする
        reasoning_effort: 推論深度（`low` / `medium` / `high` など）。`reasoning_effort`
            として送る。None や空文字なら送らない。モデルが非対応なら LiteLLM の
            `drop_params` で捨てられる

    Returns:
        実行結果

    Raises:
        LLMTimeoutError: タイムアウト時
        LLMOutputError: 応答が期待する形にならなかった時
        LLMClientError: その他の LLM 実行エラー時
    """
    with translate_llm_errors():
        async with open_model(settings) as model:
            return await agent.run(
                user_prompt,
                model=model,
                instructions=instructions,
                message_history=message_history,
                deps=deps,
                usage_limits=usage_limits,
                retries=retries,
                **_run_options(
                    settings,
                    max_tokens=max_tokens,
                    conversation_id=conversation_id,
                    reasoning_effort=reasoning_effort,
                ),
            )


def run_agent_sync(
    agent: Agent[Any, Any], settings: LLMSettings, **kwargs: Any
) -> AgentRunResult[Any]:
    """同期コードから `arun_agent` を実行する.

    `agent.run_sync` は使わない。そちらでは `sync_to_async(thread_sensitive=True)` が
    呼び出し元スレッドに戻らず、別の DB 接続になる（トランザクション内のデータも見えない）。
    `async_to_sync` なら呼び出し元スレッドが待機しながら同期処理を引き受ける。

    Args:
        agent: 実行するエージェント
        settings: 接続設定
        **kwargs: `arun_agent` のキーワード引数

    Returns:
        実行結果
    """
    return async_to_sync(arun_agent)(agent, settings, **kwargs)


def _close_client(client: AsyncOpenAI) -> None:
    """`run_stream_sync` が使ったループ（呼び出し元スレッドの現在のループ）で閉じる.

    接続はループに属するので、別のループでは閉じられない。ループが使えないときは
    `run_stream_sync` が接続を開く前に失敗しているので、何もしない。
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if loop.is_closed() or loop.is_running():
        return
    try:
        loop.run_until_complete(client.close())
    except Exception as exc:  # noqa: BLE001
        # 本文はすでに処理済みなので、ここでの失敗で応答を失敗にしない
        logger.warning("LLM クライアントを閉じられませんでした: %s", exc)


def stream_text_sync(
    agent: Agent[Any, Any],
    settings: LLMSettings,
    *,
    user_prompt: str,
    deps: Any = None,
    message_history: Sequence[ModelMessage] | None = None,
    max_tokens: int | None = None,
    conversation_id: str | None = None,
) -> Iterator[str]:
    """同期コードからテキスト出力のエージェントを実行し、本文の増分を順に返す.

    `Agent.run_stream_sync` は 1 本の長寿命タスクで実行全体を動かすので、OpenTelemetry の
    ネストとキャンセルスコープが保たれる。呼び出し元スレッドのイベントループで動くので、
    同じスレッドで読み進めて閉じること。`close()` で閉じると HTTP の接続もその場で閉じる。

    `run_stream_sync` には instructions の引数がないので、system プロンプトは
    エージェントの動的 instructions（`deps` を返す関数）で渡す。

    本文のない応答は増分なしで正常に終わる（`output_type` に `None` を許すエージェントのみ）。

    Args:
        agent: 実行するエージェント
        settings: 接続設定
        user_prompt: 今回のユーザーメッセージ
        deps: エージェントへ渡す依存
        message_history: 過去の会話履歴
        max_tokens: 出力トークン数の上限
        conversation_id: 会話 ID（`arun_agent` と同じく、省略時はサービス名）

    Yields:
        本文の増分

    Raises:
        LLMTimeoutError: タイムアウト時
        LLMOutputError: 応答が期待する形にならなかった時
        LLMClientError: その他の LLM 実行エラー時
    """
    client = _build_client(settings)
    try:
        with (
            translate_llm_errors(),
            agent.run_stream_sync(
                user_prompt,
                model=_build_model(settings, client),
                message_history=message_history,
                deps=deps,
                **_run_options(
                    settings, max_tokens=max_tokens, conversation_id=conversation_id
                ),
            ) as run,
        ):
            # 本文のない応答はここへ来た時点で実行が終わっていて、stream_text() は使えない
            if run.response.state == "incomplete":
                # yield from なので、閉じられたら内側のジェネレータもその場で閉じる
                yield from run.stream_text(
                    delta=True, debounce_by=_STREAM_DEBOUNCE_SECONDS
                )
    finally:
        _close_client(client)
