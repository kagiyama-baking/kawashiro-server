"""HNエージェントモジュール."""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.usage import UsageLimits

from integrations.hn.client import HNAlgoliaClient
from integrations.llm.config import LLMSettings
from integrations.llm.exceptions import LLMOutputError
from integrations.llm.runtime import arun_agent

from ..models import HNThread

logger = logging.getLogger(__name__)

# 読めない応答は 1 回だけ再試行する。リクエスト上限は想定外の繰り返しを止める安全弁。
ANALYSIS_OUTPUT_RETRIES = 1
ANALYSIS_REQUEST_LIMIT = 3


@dataclass(frozen=True)
class PreparedAnalysis:
    """LLM を呼ぶ前に同期処理で揃える材料（ORM・HN/Tavily・プロンプト解決の結果）."""

    settings: LLMSettings
    system_prompt: str
    user_prompt: str
    score_info: str
    comments_text: str
    sources: list[dict[str, Any]] = field(default_factory=list)


def hn_conversation_id(thread: HNThread) -> str:
    """スレッドの調査の会話 ID を返す.

    Langfuse はこれをセッションとして扱うので、Orchestrator とサブエージェントで揃えて
    1 つのスレッドの調査を 1 つのセッションにまとめる。
    """
    return f"hn-thread/{thread.hn_id}"


def _last_response_text(messages: list[ModelMessage]) -> str:
    """実行中の最後の応答本文を返す（本文のない応答は飛ばす）."""
    for message in reversed(messages):
        if isinstance(message, ModelResponse) and message.text:
            return message.text
    return ""


async def run_analysis(
    agent: Agent[None, Any],
    settings: LLMSettings,
    system_prompt: str,
    user_prompt: str,
    fallback: Callable[[str], dict[str, Any]],
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """構造化出力のエージェントを実行し、結果を dict で返す.

    再試行しても応答を読めないときは、調査済みマークと Slack 通知の流れを止めないよう
    `fallback` に最後の応答本文を渡した結果を返す。結果の dict には LLM が返したキーだけを
    入れる（スキーマの既定値は足さない）。

    Args:
        agent: 実行するエージェント
        settings: 接続設定
        system_prompt: システムプロンプト
        user_prompt: ユーザープロンプト
        fallback: 最後の応答本文から代わりの分析結果を作る関数
        conversation_id: 会話 ID（`hn_conversation_id`）

    Returns:
        分析結果

    Raises:
        LLMClientError: 接続エラーなど、読めない応答を受け取った以外の失敗時
    """
    with capture_run_messages() as messages:
        try:
            result = await arun_agent(
                agent,
                settings,
                user_prompt=user_prompt,
                instructions=system_prompt,
                retries={"output": ANALYSIS_OUTPUT_RETRIES},
                usage_limits=UsageLimits(request_limit=ANALYSIS_REQUEST_LIMIT),
                conversation_id=conversation_id,
            )
        except LLMOutputError as exc:
            # 不正な HTTP 応答などでモデルの応答を受け取れていないなら、分析の失敗として送出する
            if not any(isinstance(message, ModelResponse) for message in messages):
                raise
            logger.warning(
                "%s の分析結果のパースに失敗、フォールバック形式を使用: %s",
                agent.name,
                exc,
            )
            return fallback(_last_response_text(messages))
    return result.output.model_dump(mode="json", exclude_unset=True)


def _strip_html(text: str) -> str:
    """HTMLタグを除去."""
    return re.sub(r"<[^>]+>", "", text)


def fetch_comments_text(
    hn_client: HNAlgoliaClient,
    thread: HNThread,
    max_comments: int = 50,
    max_depth: int = 2,
) -> str:
    """スレッドのコメントをテキストとして取得.

    Args:
        hn_client: HN Algoliaクライアント
        thread: 対象スレッド
        max_comments: 取得するコメントの上限数
        max_depth: コメントツリーの最大深度

    Returns:
        コメントテキスト（改行区切り）
    """
    comments = hn_client.get_comments(thread.hn_id, max_depth=max_depth)
    flat = hn_client.flatten_comments(comments)

    texts = []
    for comment in flat[:max_comments]:
        if comment.text and comment.author:
            clean_text = _strip_html(comment.text)
            texts.append(f"[{comment.author}]: {clean_text}")

    return "\n\n".join(texts)
