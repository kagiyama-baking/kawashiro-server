"""Devil's Advocate Agent — 新技術・Show HN等に対する辛口・批判的視点を抽出."""

import logging
from typing import Any

from asgiref.sync import sync_to_async
from langfuse import observe
from pydantic_ai import Agent, PromptedOutput

from integrations.hn.client import HNAlgoliaClient
from integrations.langfuse.client import resolve_prompt
from integrations.llm.config import get_llm_settings

from ..models import HNAgentConfig, HNThread
from . import (
    PreparedAnalysis,
    fetch_comments_text,
    hn_conversation_id,
    run_analysis,
)
from .schemas import DevilsAdvocateAnalysis

logger = logging.getLogger(__name__)

MAX_COMMENTS_FOR_ANALYSIS = 50

DEVILS_ADVOCATE_AGENT = Agent(
    name="hn-devils-advocate",
    # Langfuse のプロンプトが JSON の形を指示するので、スキーマは送らず検証にだけ使う
    output_type=PromptedOutput(DevilsAdvocateAnalysis, template=False),
)


def _fallback_analysis(raw: str) -> dict[str, Any]:
    """応答を読めなかったときの分析結果."""
    return {
        "concerns": [],
        "past_cases": [],
        "critical_comments": [],
        "summary": raw[:500],
    }


class DevilsAdvocateAgent:
    """HNスレッドに対する批判的・懐疑的な視点を抽出するエージェント.

    主に「新しい技術の発表（Show HN）」「アーキテクチャ議論」で Orchestrator から
    呼ばれることを想定。懸念点・トレードオフ・過去の類似事例・辛口コメントを
    JSON 形式で構造化して返す。
    """

    def __init__(
        self,
        hn_client: HNAlgoliaClient | None = None,
    ):
        """初期化."""
        self._hn_client = hn_client

    @property
    def hn_client(self) -> HNAlgoliaClient:
        """HNクライアントを取得（遅延初期化）."""
        if self._hn_client is None:
            self._hn_client = HNAlgoliaClient()
        return self._hn_client

    def _fetch_comments_text(self, thread: HNThread) -> str:
        """スレッドのコメントをテキストとして取得."""
        return fetch_comments_text(
            self.hn_client, thread, max_comments=MAX_COMMENTS_FOR_ANALYSIS
        )

    def _prepare(self, thread: HNThread) -> PreparedAnalysis:
        """LLM を呼ぶ前の同期処理（ORM・HN 取得・プロンプト解決）."""
        comments_text = self._fetch_comments_text(thread)

        snapshot = thread.latest_snapshot
        score_info = ""
        if snapshot:
            score_info = (
                f"スコア: {snapshot.score}, コメント数: {snapshot.num_comments}"
            )

        agent_config = HNAgentConfig.objects.get_active_config()

        user_prompt = resolve_prompt(
            agent_config.devils_advocate_user_prompt,
            title=thread.title,
            url=thread.url or "(self-post)",
            author=thread.author,
            score_info=score_info,
            comments_section=self._format_comments_section(comments_text),
        )
        system_prompt = resolve_prompt(agent_config.devils_advocate_system_prompt)

        return PreparedAnalysis(
            settings=get_llm_settings("devils_advocate"),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            score_info=score_info,
            comments_text=comments_text,
        )

    @observe(name="hn-agent/devils-advocate", as_type="tool")
    async def analyze(self, thread: HNThread) -> dict:
        """スレッドに対する辛口・批判的視点を抽出する.

        Args:
            thread: 分析対象スレッド

        Returns:
            批判的分析結果
        """
        logger.info("Devil's Advocate 分析開始: [%d] %s", thread.hn_id, thread.title)

        prepared = await sync_to_async(self._prepare)(thread)

        analysis = await run_analysis(
            DEVILS_ADVOCATE_AGENT,
            prepared.settings,
            prepared.system_prompt,
            prepared.user_prompt,
            _fallback_analysis,
            conversation_id=hn_conversation_id(thread),
        )

        result = {
            "thread_hn_id": thread.hn_id,
            "thread_title": thread.title,
            "thread_url": thread.url,
            "score_info": prepared.score_info,
            "analysis": analysis,
            "comments_analyzed": min(
                len([c for c in prepared.comments_text.split("\n\n") if c]),
                MAX_COMMENTS_FOR_ANALYSIS,
            ),
        }

        logger.info("Devil's Advocate 分析完了: [%d] %s", thread.hn_id, thread.title)
        return result

    def _format_comments_section(self, comments_text: str) -> str:
        """HN コメントセクションの文字列を構築（空なら空文字）."""
        if not comments_text:
            return ""
        return (
            "\n## HNコメント（抜粋）\n"
            "<hn_comments>\n"
            f"{comments_text[:3000]}\n"
            "</hn_comments>"
        )
