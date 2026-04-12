"""Detective Agent — スレッド急上昇の原因を調査."""

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


class DetectiveAgent:
    """スレッドの急上昇原因を調査するエージェント."""

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
            self._llm_client = LLMClient(service_name="detective")
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

    def _search_background(self, thread: HNThread) -> list[dict[str, Any]]:
        """Tavilyでスレッドの背景情報を検索.

        Args:
            thread: 対象スレッド

        Returns:
            検索結果のリスト
        """
        client = self.tavily_client
        if client is None:
            return []

        try:
            query = f"{thread.title} {thread.author}"
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
            logger.warning("Tavily検索に失敗: [%d] %s", thread.hn_id, thread.title)
            return []

    @observe(name="hn-agent/detective", as_type="tool")
    def investigate(self, thread: HNThread) -> dict:
        """スレッドの調査を実行.

        Args:
            thread: 調査対象スレッド

        Returns:
            調査結果
        """
        logger.info("Detective調査開始: [%d] %s", thread.hn_id, thread.title)

        comments_text = self._fetch_comments_text(thread)
        background = self._search_background(thread)

        snapshot = thread.latest_snapshot
        score_info = ""
        if snapshot:
            score_info = (
                f"スコア: {snapshot.score}, コメント数: {snapshot.num_comments}"
            )

        agent_config = HNAgentConfig.objects.get_active_config()

        user_prompt = resolve_prompt(
            agent_config.detective_user_prompt,
            title=thread.title,
            url=thread.url or "(self-post)",
            author=thread.author,
            score_info=score_info,
            background_section=self._format_background_section(background),
            comments_section=self._format_comments_section(comments_text),
        )
        system_prompt = resolve_prompt(agent_config.detective_system_prompt)

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
            "background_sources": background,
            "comments_analyzed": min(
                len(comments_text.split("\n\n")), MAX_COMMENTS_FOR_ANALYSIS
            ),
        }

        thread.is_investigated = True
        thread.save(update_fields=["is_investigated"])

        logger.info("Detective調査完了: [%d] %s", thread.hn_id, thread.title)
        return result

    def _format_background_section(self, background: list[dict[str, Any]]) -> str:
        """Web 背景情報セクションの文字列を構築（空なら空文字）."""
        if not background:
            return ""
        lines = ["\n## Web上の背景情報"]
        for bg in background:
            lines.append(f"- [{bg['title']}]({bg['url']})")
            lines.append(f"  {bg['content']}")
        return "\n".join(lines)

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
        # ```json ... ``` で囲まれている場合を処理
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # ```json 行を除去
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            parsed = json.loads(text)
            # 必須キーの存在確認
            if "title_ja" in parsed and "comment_highlights" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        logger.warning("Detective分析結果のJSONパースに失敗、フォールバック形式を使用")
        return {
            "title_ja": "",
            "why_trending": raw[:500],
            "background": "",
            "comment_highlights": [],
            "summary": "",
        }
