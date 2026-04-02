"""HNエージェントモジュール."""

import re

from integrations.hn.client import HNAlgoliaClient

from ..models import HNThread


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
