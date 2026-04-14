"""Devil's Advocate Agent — 新技術・Show HN等に対する辛口・批判的視点を抽出."""

import json
import logging
from typing import Any

from langfuse import observe

from integrations.hn.client import HNAlgoliaClient
from integrations.langfuse.client import resolve_prompt
from integrations.llm.client import LLMClient

from ..models import HNAgentConfig, HNThread

logger = logging.getLogger(__name__)

MAX_COMMENTS_FOR_ANALYSIS = 50


class DevilsAdvocateAgent:
    """HNスレッドに対する批判的・懐疑的な視点を抽出するエージェント.

    主に「新しい技術の発表（Show HN）」「アーキテクチャ議論」で Orchestrator から
    呼ばれることを想定。懸念点・トレードオフ・過去の類似事例・辛口コメントを
    JSON 形式で構造化して返す。
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        hn_client: HNAlgoliaClient | None = None,
    ):
        """初期化."""
        self._llm_client = llm_client
        self._hn_client = hn_client

    @property
    def llm_client(self) -> LLMClient:
        """LLMクライアントを取得（遅延初期化）."""
        if self._llm_client is None:
            self._llm_client = LLMClient(service_name="devils_advocate")
        return self._llm_client

    @property
    def hn_client(self) -> HNAlgoliaClient:
        """HNクライアントを取得（遅延初期化）."""
        if self._hn_client is None:
            self._hn_client = HNAlgoliaClient()
        return self._hn_client

    def _fetch_comments_text(self, thread: HNThread) -> str:
        """スレッドのコメントをテキストとして取得."""
        from . import fetch_comments_text

        return fetch_comments_text(
            self.hn_client, thread, max_comments=MAX_COMMENTS_FOR_ANALYSIS
        )

    @observe(name="hn-agent/devils-advocate", as_type="tool")
    def analyze(self, thread: HNThread) -> dict:
        """スレッドに対する辛口・批判的視点を抽出する.

        Args:
            thread: 分析対象スレッド

        Returns:
            批判的分析結果
        """
        logger.info("Devil's Advocate 分析開始: [%d] %s", thread.hn_id, thread.title)

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

        raw_analysis = self.llm_client.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )

        analysis = self._parse_analysis(raw_analysis)

        result = {
            "thread_hn_id": thread.hn_id,
            "thread_title": thread.title,
            "thread_url": thread.url,
            "score_info": score_info,
            "analysis": analysis,
            "comments_analyzed": min(
                len([c for c in comments_text.split("\n\n") if c]),
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

    def _parse_analysis(self, raw: str) -> dict[str, Any]:
        """LLMのJSON応答をパース.

        Args:
            raw: LLMの生テキスト応答

        Returns:
            パース済み辞書。失敗時はフォールバック形式
        """
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            parsed = json.loads(text)
            if "concerns" in parsed and "critical_comments" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        logger.warning(
            "Devil's Advocate 分析結果のJSONパースに失敗、フォールバック形式を使用"
        )
        return {
            "concerns": [],
            "past_cases": [],
            "critical_comments": [],
            "summary": raw[:500],
        }
