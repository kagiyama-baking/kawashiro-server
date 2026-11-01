"""PydanticAI の実行基盤.

LiteLLM Proxy 経由のモデル生成、同期コードからの実行、例外の変換をまとめる。
エージェントの定義は各機能に置き、実行はここの関数だけを通す。
"""

from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
from typing import Any

from asgiref.sync import async_to_sync
from openai import AsyncOpenAI
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
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from .config import LLMSettings
from .exceptions import LLMClientError, LLMOutputError, LLMTimeoutError

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


@asynccontextmanager
async def open_model(settings: LLMSettings) -> AsyncIterator[OpenAIChatModel]:
    """LiteLLM Proxy へ接続するモデルを開く.

    AsyncOpenAI の接続はイベントループに属し、同期コードからの実行では毎回ループが
    変わるので、クライアントは実行ごとに作って閉じる。
    """
    async with AsyncOpenAI(
        base_url=settings.proxy_base_url,
        # キー未設定でも送信し、認証の判断は LiteLLM に任せる（SDK は空文字を拒否する）
        api_key=settings.proxy_api_key or _MISSING_API_KEY,
        timeout=settings.timeout,
    ) as client:
        yield OpenAIChatModel(
            settings.model_alias,
            provider=LiteLLMProvider(openai_client=client),
            profile=_LITELLM_PROFILE,
        )


def _build_model_settings(
    settings: LLMSettings, max_tokens: int | None
) -> ModelSettings:
    """LiteLLM へ送るリクエストパラメータを組み立てる."""
    extra_body = {
        "metadata": {
            "service_name": settings.service_name,
            "environment": settings.environment,
        }
    }
    if max_tokens is None:
        return ModelSettings(extra_body=extra_body)
    return ModelSettings(extra_body=extra_body, max_tokens=max_tokens)


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
                model_settings=_build_model_settings(settings, max_tokens),
                usage_limits=usage_limits,
                retries=retries,
                capabilities=[_TreatEmptyResponseAsFinished()],
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
