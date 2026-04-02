"""Tavily Web検索APIクライアント."""

import logging
from dataclasses import dataclass

import requests

from .config import get_tavily_settings
from .exceptions import TavilyAPIError

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class TavilySearchResult:
    """Tavily検索結果."""

    title: str
    url: str
    content: str
    score: float


class TavilyClient:
    """Tavily Web検索APIクライアント."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int | None = None,
    ):
        """クライアントを初期化.

        設定の優先順位:
        1. 引数で明示的に指定された値
        2. データベースの有効な設定

        Args:
            api_key: Tavily APIキー。省略時はDB設定から取得
            timeout: タイムアウト秒数。省略時はDB設定から取得

        Raises:
            TavilyConfigurationError: DB設定がない、またはAPIキーが未設定の場合
        """
        db_settings = get_tavily_settings()
        self.api_key = api_key or db_settings.api_key
        self.timeout = timeout or db_settings.timeout

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
    ) -> dict:
        """Web検索を実行.

        Args:
            query: 検索クエリ
            max_results: 最大結果数
            search_depth: 検索深度（"basic" or "advanced"）
            include_answer: AI生成の回答を含めるか

        Returns:
            検索結果の辞書

        Raises:
            TavilyAPIError: API呼び出しエラー
        """
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": include_answer,
        }

        try:
            response = requests.post(
                TAVILY_API_URL,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise TavilyAPIError(f"Tavily API呼び出しに失敗しました: {e}") from e

    def search_context(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[TavilySearchResult]:
        """Web検索を実行し、構造化された結果を返す.

        Args:
            query: 検索クエリ
            max_results: 最大結果数

        Returns:
            TavilySearchResultのリスト
        """
        raw = self.search(query, max_results=max_results)

        results = []
        for item in raw.get("results", []):
            results.append(
                TavilySearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    score=item.get("score", 0.0),
                )
            )

        logger.info("Tavily検索完了: query='%s', 結果%d件", query, len(results))
        return results
