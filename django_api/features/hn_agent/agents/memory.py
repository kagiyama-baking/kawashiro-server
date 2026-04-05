"""Memory Agent — 過去スレッドとの類似性を検索."""

import logging

from integrations.llm.openai_client import OpenAIClient

from ..models import HNAgentConfig, HNThread, Investigation, ThreadEmbedding

logger = logging.getLogger(__name__)

MAX_SIMILAR_RESULTS = 5


class MemoryAgent:
    """pgvectorを使って過去スレッドとの類似性を検索するエージェント."""

    def __init__(self, openai_client: OpenAIClient | None = None):
        """初期化.

        Args:
            openai_client: embedding生成用OpenAIクライアント
        """
        self._openai_client = openai_client

    @property
    def openai_client(self) -> OpenAIClient:
        """OpenAIクライアントを取得（遅延初期化）."""
        if self._openai_client is None:
            self._openai_client = OpenAIClient()
        return self._openai_client

    def _get_similarity_threshold(self) -> float:
        """類似度閾値を取得."""
        try:
            config = HNAgentConfig.objects.get_active_config()
            return config.similarity_threshold
        except HNAgentConfig.DoesNotExist:
            return 0.85

    def _get_embedding_dimensions(self) -> int | None:
        """Embedding次元数を取得."""
        try:
            config = HNAgentConfig.objects.get_active_config()
            return config.embedding_dimensions
        except HNAgentConfig.DoesNotExist:
            return None

    def generate_embedding(self, text: str) -> list[float]:
        """テキストからembeddingを生成.

        モデル名はOpenAI API設定から、次元数はHN Agent設定から取得される。

        Args:
            text: 埋め込み対象のテキスト

        Returns:
            embeddingベクトル
        """
        dimensions = self._get_embedding_dimensions()
        return self.openai_client.generate_embedding(text, dimensions=dimensions)

    def ensure_embedding(self, thread: HNThread) -> ThreadEmbedding:
        """スレッドのembeddingを確保（存在しなければ生成）.

        Args:
            thread: 対象スレッド

        Returns:
            ThreadEmbeddingインスタンス
        """
        existing = ThreadEmbedding.objects.filter(thread=thread).first()
        if existing is not None:
            return existing

        embedding_text = f"{thread.title} {thread.url}"
        vector = self.generate_embedding(embedding_text)

        return ThreadEmbedding.objects.create(
            thread=thread,
            embedding=vector,
        )

    def find_similar_threads(
        self,
        thread: HNThread,
        threshold: float | None = None,
        max_results: int = MAX_SIMILAR_RESULTS,
    ) -> list[dict]:
        """過去の類似スレッドを検索.

        Args:
            thread: 検索対象スレッド
            threshold: 類似度閾値（0-1）。省略時はDB設定から取得
            max_results: 最大結果数

        Returns:
            類似スレッド情報のリスト
        """
        from pgvector.django import CosineDistance

        if threshold is None:
            threshold = self._get_similarity_threshold()

        # 対象スレッドのembeddingを確保
        thread_embedding = self.ensure_embedding(thread)

        # cosine similarity検索（自身を除外）
        similar = (
            ThreadEmbedding.objects.exclude(thread=thread)
            .annotate(distance=CosineDistance("embedding", thread_embedding.embedding))
            .filter(distance__lt=(1 - threshold))
            .order_by("distance")[:max_results]
        )

        results = []
        for item in similar:
            similarity = 1 - item.distance
            results.append(
                {
                    "hn_id": item.thread.hn_id,
                    "title": item.thread.title,
                    "url": item.thread.url,
                    "similarity": round(similarity, 4),
                    "first_seen": item.thread.first_seen.isoformat(),
                    "was_investigated": item.thread.is_investigated,
                }
            )

        return results

    def investigate(self, thread: HNThread) -> dict:
        """スレッドのメモリ調査を実行.

        過去の類似スレッドを検索し、結果をInvestigationに保存する。

        Args:
            thread: 調査対象スレッド

        Returns:
            調査結果
        """
        logger.info("Memory調査開始: [%d] %s", thread.hn_id, thread.title)

        similar_threads = self.find_similar_threads(thread)

        result = {
            "thread_hn_id": thread.hn_id,
            "thread_title": thread.title,
            "similar_threads": similar_threads,
            "has_similar": len(similar_threads) > 0,
            "summary": self._build_summary(thread, similar_threads),
        }

        Investigation.objects.create(
            thread=thread,
            agent_type="memory",
            result=result,
        )

        logger.info(
            "Memory調査完了: [%d] 類似スレッド%d件",
            thread.hn_id,
            len(similar_threads),
        )

        return result

    def _build_summary(self, thread: HNThread, similar_threads: list[dict]) -> str:
        """調査結果のサマリーを生成."""
        if not similar_threads:
            return f"[{thread.hn_id}] '{thread.title}' に類似する過去スレッドは見つかりませんでした。"

        lines = [
            f"[{thread.hn_id}] '{thread.title}' に類似する過去スレッドが{len(similar_threads)}件見つかりました:",
        ]
        for st in similar_threads:
            lines.append(
                f"  - [{st['hn_id']}] '{st['title']}' (類似度: {st['similarity']:.2%})"
            )

        return "\n".join(lines)
