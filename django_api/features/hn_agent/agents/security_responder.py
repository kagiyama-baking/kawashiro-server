"""Security Responder Agent — 脆弱性・CVEスレッドの対応指針を整理."""

import json
import logging
from typing import Any

from langfuse import observe

from integrations.hn.client import HNAlgoliaClient
from integrations.langfuse.client import resolve_prompt
from integrations.llm.client import LLMClient
from integrations.tavily.client import TavilyClient
from integrations.tavily.exceptions import TavilyError

from ..models import HNAgentConfig, HNThread

logger = logging.getLogger(__name__)

MAX_COMMENTS_FOR_ANALYSIS = 50


class SecurityResponderAgent:
    """セキュリティインシデント特化のエージェント.

    Orchestrator からセキュリティ話題（脆弱性・CVE・情報漏洩・ハッキング）の
    スレッドで呼び出されることを想定。影響範囲・回避策・公式パッチ・CVE ID を
    JSON 形式で構造化して返す。Tavily で CVE / patch 情報を補強する。
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        hn_client: HNAlgoliaClient | None = None,
        tavily_client: TavilyClient | None = None,
    ):
        """初期化."""
        self._llm_client = llm_client
        self._hn_client = hn_client
        self._tavily_client = tavily_client

    @property
    def llm_client(self) -> LLMClient:
        """LLMクライアントを取得（遅延初期化）."""
        if self._llm_client is None:
            self._llm_client = LLMClient(service_name="security_responder")
        return self._llm_client

    @property
    def hn_client(self) -> HNAlgoliaClient:
        """HNクライアントを取得（遅延初期化）."""
        if self._hn_client is None:
            self._hn_client = HNAlgoliaClient()
        return self._hn_client

    @property
    def tavily_client(self) -> TavilyClient | None:
        """Tavilyクライアントを取得（遅延初期化、設定なしの場合はNone）."""
        if self._tavily_client is None:
            try:
                self._tavily_client = TavilyClient()
            except TavilyError:
                logger.warning("Tavily APIキーが未設定のためWeb検索をスキップ")
                return None
        return self._tavily_client

    def _fetch_comments_text(self, thread: HNThread) -> str:
        """スレッドのコメントをテキストとして取得."""
        from . import fetch_comments_text

        return fetch_comments_text(
            self.hn_client, thread, max_comments=MAX_COMMENTS_FOR_ANALYSIS
        )

    def _search_security_context(self, thread: HNThread) -> list[dict[str, Any]]:
        """Tavily でセキュリティ関連情報を検索.

        CVE / advisory / patch / workaround を優先して取得する。

        Args:
            thread: 対象スレッド

        Returns:
            検索結果のリスト
        """
        client = self.tavily_client
        if client is None:
            return []

        try:
            query = f"{thread.title} CVE advisory patch workaround"
            results = client.search_context(query, max_results=3)
            return [
                {
                    "title": r.title,
                    "url": r.url,
                    "content": r.content[:500],
                }
                for r in results
            ]
        except TavilyError:
            logger.warning("Tavily 検索に失敗: [%d] %s", thread.hn_id, thread.title)
            return []

    @observe(name="hn-agent/security-responder", as_type="tool")
    def analyze(self, thread: HNThread) -> dict:
        """セキュリティインシデントの整理を実行.

        Args:
            thread: 対象スレッド

        Returns:
            整理結果
        """
        logger.info("Security Responder 分析開始: [%d] %s", thread.hn_id, thread.title)

        comments_text = self._fetch_comments_text(thread)
        search_sources = self._search_security_context(thread)

        snapshot = thread.latest_snapshot
        score_info = ""
        if snapshot:
            score_info = (
                f"スコア: {snapshot.score}, コメント数: {snapshot.num_comments}"
            )

        agent_config = HNAgentConfig.objects.get_active_config()

        user_prompt = resolve_prompt(
            agent_config.security_responder_user_prompt,
            title=thread.title,
            url=thread.url or "(self-post)",
            author=thread.author,
            score_info=score_info,
            comments_section=self._format_comments_section(comments_text),
            search_section=self._format_search_section(search_sources),
        )
        system_prompt = resolve_prompt(agent_config.security_responder_system_prompt)

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
            "search_sources": search_sources,
            "comments_analyzed": min(
                len([c for c in comments_text.split("\n\n") if c]),
                MAX_COMMENTS_FOR_ANALYSIS,
            ),
        }

        logger.info("Security Responder 分析完了: [%d] %s", thread.hn_id, thread.title)
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

    def _format_search_section(self, sources: list[dict[str, Any]]) -> str:
        """Tavily 検索結果セクションの文字列を構築（空なら空文字）."""
        if not sources:
            return ""
        lines = ["\n## Web上のセキュリティ情報"]
        for src in sources:
            lines.append(f"- [{src['title']}]({src['url']})")
            lines.append(f"  {src['content']}")
        return "\n".join(lines)

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
            if "severity" in parsed and "summary" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        logger.warning(
            "Security Responder 分析結果のJSONパースに失敗、フォールバック形式を使用"
        )
        return {
            "cve_ids": [],
            "affected": [],
            "workarounds": [],
            "official_patch": {"available": False, "version": None, "url": None},
            "severity": "unknown",
            "summary": raw[:500],
        }
