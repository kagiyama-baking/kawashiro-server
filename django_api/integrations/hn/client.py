"""Hacker News Algolia APIクライアント."""

import logging
from dataclasses import dataclass
from typing import Any

import requests

from .exceptions import HNNetworkError, HNParseError, HNTimeoutError

logger = logging.getLogger(__name__)

# Algolia HN Search API
# https://hn.algolia.com/api
ALGOLIA_API_BASE_URL = "https://hn.algolia.com/api/v1"
HN_TIMEOUT = 15


@dataclass(frozen=True)
class HNStory:
    """HNストーリーのデータクラス."""

    hn_id: int
    title: str
    url: str
    author: str
    score: int
    num_comments: int
    created_at: str


@dataclass(frozen=True)
class HNComment:
    """HNコメントのデータクラス."""

    hn_id: int
    author: str | None
    text: str | None
    parent_id: int | None
    children: list["HNComment"]


class HNAlgoliaClient:
    """Hacker News Algolia APIクライアント."""

    def __init__(self, timeout: int = HN_TIMEOUT):
        """クライアントを初期化.

        Args:
            timeout: HTTPリクエストのタイムアウト秒数
        """
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GETリクエストを送信.

        Args:
            path: APIパス（ベースURL相対）
            params: クエリパラメータ

        Returns:
            レスポンスのJSONデータ

        Raises:
            HNNetworkError: 接続エラー
            HNTimeoutError: タイムアウト
            HNParseError: レスポンス解析エラー
        """
        url = f"{ALGOLIA_API_BASE_URL}/{path}"

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.ConnectionError as e:
            raise HNNetworkError("HN Algolia APIへの接続に失敗しました") from e
        except requests.Timeout as e:
            raise HNTimeoutError(
                "HN Algolia APIへのリクエストがタイムアウトしました"
            ) from e
        except requests.HTTPError as e:
            raise HNNetworkError(
                f"HN Algolia APIがエラーを返しました: {e.response.status_code}"
            ) from e
        except ValueError as e:
            raise HNParseError("HN Algolia APIのレスポンス解析に失敗しました") from e

    def get_front_page_stories(
        self,
        tags: str = "front_page",
        hits_per_page: int = 30,
    ) -> list[HNStory]:
        """フロントページのストーリーを取得.

        Args:
            tags: 検索タグ（デフォルト: front_page）
            hits_per_page: 取得件数

        Returns:
            HNStoryのリスト
        """
        data = self._get(
            "search",
            params={
                "tags": tags,
                "hitsPerPage": hits_per_page,
            },
        )

        stories = []
        for hit in data.get("hits", []):
            story = HNStory(
                hn_id=int(hit["objectID"]),
                title=hit.get("title", ""),
                url=hit.get("url") or "",
                author=hit.get("author", ""),
                score=hit.get("points") or 0,
                num_comments=hit.get("num_comments") or 0,
                created_at=hit.get("created_at", ""),
            )
            stories.append(story)

        logger.info("HNフロントページから%d件のストーリーを取得", len(stories))
        return stories

    def get_item(self, item_id: int) -> dict[str, Any]:
        """アイテム（ストーリーまたはコメント）を取得.

        Args:
            item_id: HNアイテムID

        Returns:
            アイテムデータの辞書
        """
        return self._get(f"items/{item_id}")

    def get_comments(self, story_id: int, max_depth: int = 3) -> list[HNComment]:
        """ストーリーのコメントを再帰的に取得.

        Args:
            story_id: ストーリーID
            max_depth: コメントツリーの最大深度

        Returns:
            HNCommentのリスト（ツリー構造）
        """
        item = self.get_item(story_id)
        children = item.get("children", [])
        return self._parse_comments(children, depth=0, max_depth=max_depth)

    def _parse_comments(
        self,
        children: list[dict[str, Any]],
        depth: int,
        max_depth: int,
    ) -> list[HNComment]:
        """コメントツリーを再帰的にパース.

        Args:
            children: 子コメントのリスト
            depth: 現在の深度
            max_depth: 最大深度

        Returns:
            HNCommentのリスト
        """
        comments = []
        for child in children:
            nested = []
            if depth < max_depth:
                nested = self._parse_comments(
                    child.get("children", []),
                    depth=depth + 1,
                    max_depth=max_depth,
                )

            comment = HNComment(
                hn_id=child.get("id", 0),
                author=child.get("author"),
                text=child.get("text"),
                parent_id=child.get("parent_id"),
                children=nested,
            )
            comments.append(comment)

        return comments

    def flatten_comments(self, comments: list[HNComment]) -> list[HNComment]:
        """ツリー構造のコメントをフラットなリストに変換.

        Args:
            comments: ツリー構造のコメントリスト

        Returns:
            フラットなコメントリスト
        """
        flat: list[HNComment] = []
        for comment in comments:
            flat.append(comment)
            if comment.children:
                flat.extend(self.flatten_comments(comment.children))
        return flat
