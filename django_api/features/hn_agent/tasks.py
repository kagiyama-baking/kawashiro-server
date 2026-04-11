"""HN Agent Celeryタスク."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from langfuse import observe

from integrations.hn.client import HNAlgoliaClient

from .models import HNAgentConfig, HNThread, HNThreadSnapshot

logger = logging.getLogger(__name__)

# デフォルト設定値（DB設定がない場合のフォールバック）
DEFAULT_SCORE_THRESHOLD = 100
DEFAULT_VELOCITY_THRESHOLD = 50  # ポイント/時間


def _get_score_threshold() -> int:
    """スコア閾値を取得（DB設定優先、なければデフォルト）."""
    try:
        config = HNAgentConfig.objects.get_active_config()
        return config.score_threshold
    except HNAgentConfig.DoesNotExist:
        return DEFAULT_SCORE_THRESHOLD


def _get_velocity_threshold() -> float:
    """スコア上昇速度閾値を取得（DB設定優先、なければデフォルト）."""
    try:
        config = HNAgentConfig.objects.get_active_config()
        return config.velocity_threshold
    except HNAgentConfig.DoesNotExist:
        return DEFAULT_VELOCITY_THRESHOLD


def _calculate_score_velocity(thread: HNThread, current_score: int) -> float | None:
    """スコアの上昇速度を計算（ポイント/時間）.

    Args:
        thread: HNスレッド
        current_score: 現在のスコア

    Returns:
        スコア上昇速度（ポイント/時間）。比較対象がない場合はNone
    """
    previous = thread.snapshots.order_by("-fetched_at").first()
    if previous is None:
        return None

    time_diff = timezone.now() - previous.fetched_at
    hours = time_diff.total_seconds() / 3600

    if hours < 0.01:  # 36秒未満の差は無視
        return None

    score_diff = current_score - previous.score
    return score_diff / hours


def _calculate_comment_velocity(
    thread: HNThread, current_comments: int
) -> float | None:
    """コメント増加率を計算（コメント/時間）.

    Args:
        thread: HNスレッド
        current_comments: 現在のコメント数

    Returns:
        コメント増加率（コメント/時間）。比較対象がない場合はNone
    """
    previous = thread.snapshots.order_by("-fetched_at").first()
    if previous is None:
        return None

    time_diff = timezone.now() - previous.fetched_at
    hours = time_diff.total_seconds() / 3600

    if hours < 0.01:
        return None

    comment_diff = current_comments - previous.num_comments
    return comment_diff / hours


@shared_task(name="hn_agent.poll_front_page")
def poll_front_page(auto_investigate: bool = True) -> dict:
    """HNフロントページをポーリングしてスナップショットを記録.

    Args:
        auto_investigate: 閾値超えスレッドのOrchestrator自動起動を行うか

    Returns:
        実行結果のサマリー
    """
    return _poll_front_page_impl(auto_investigate)


@observe(name="hn-agent/scheduled-run")
def _poll_front_page_impl(auto_investigate: bool) -> dict:
    """poll_front_pageの実装（Langfuseトレース対応）."""
    client = HNAlgoliaClient()
    stories = client.get_front_page_stories()

    created_count = 0
    snapshot_count = 0
    triggered_threads = []

    score_threshold = _get_score_threshold()
    velocity_threshold = _get_velocity_threshold()

    for story in stories:
        # スレッドの作成または取得
        thread, created = HNThread.objects.get_or_create(
            hn_id=story.hn_id,
            defaults={
                "title": story.title,
                "url": story.url,
                "author": story.author,
            },
        )

        if created:
            created_count += 1

        # スコア上昇速度を計算（スナップショット保存前に）
        score_velocity = _calculate_score_velocity(thread, story.score)
        comment_velocity = _calculate_comment_velocity(thread, story.num_comments)

        # スナップショットを記録
        HNThreadSnapshot.objects.create(
            thread=thread,
            score=story.score,
            num_comments=story.num_comments,
        )
        snapshot_count += 1

        # 閾値チェック: 調査トリガー（調査済みスレッドはスキップ）
        if thread.is_investigated:
            continue

        should_investigate = False

        if story.score >= score_threshold:
            should_investigate = True
            logger.info(
                "スコア閾値超え: [%d] %s (score=%d, threshold=%d)",
                story.hn_id,
                story.title,
                story.score,
                score_threshold,
            )

        if score_velocity is not None and score_velocity >= velocity_threshold:
            should_investigate = True
            logger.info(
                "スコア急上昇: [%d] %s (velocity=%.1f/h, threshold=%.1f/h)",
                story.hn_id,
                story.title,
                score_velocity,
                velocity_threshold,
            )

        if should_investigate:
            triggered_threads.append(
                {
                    "hn_id": story.hn_id,
                    "title": story.title,
                    "score": story.score,
                    "score_velocity": score_velocity,
                    "comment_velocity": comment_velocity,
                }
            )

    # Orchestratorを同期実行（1トレースにまとめるため）
    if auto_investigate and triggered_threads:
        _run_triggered_investigations(triggered_threads)

    logger.info(
        "ポーリング完了: 新規=%d, スナップショット=%d, トリガー=%d",
        created_count,
        snapshot_count,
        len(triggered_threads),
    )

    return {
        "stories_fetched": len(stories),
        "new_threads": created_count,
        "snapshots_created": snapshot_count,
        "triggered_threads": triggered_threads,
    }


def _run_triggered_investigations(triggered_threads: list[dict]) -> None:
    """閾値超えスレッドに対してOrchestratorを同期実行."""
    from .orchestrator import Orchestrator

    orchestrator = Orchestrator()
    for triggered_thread in triggered_threads:
        hn_id = triggered_thread["hn_id"]
        try:
            thread = HNThread.objects.get(hn_id=hn_id)
        except HNThread.DoesNotExist:
            continue

        if thread.is_investigated:
            continue

        try:
            orchestrator.investigate(thread)
        except Exception:
            logger.exception("Orchestrator実行エラー: [%d]", hn_id)


@shared_task(name="hn_agent.run_orchestrator")
def run_orchestrator(hn_id: int) -> dict:
    """指定スレッドに対してOrchestratorを実行.

    Args:
        hn_id: HNスレッドID

    Returns:
        Orchestratorの実行結果サマリー
    """
    return _run_orchestrator_impl(hn_id)


@observe(name="hn-agent/orchestrator")
def _run_orchestrator_impl(hn_id: int) -> dict:
    """run_orchestratorの実装（@observeトレーシング対応）."""
    from .orchestrator import Orchestrator

    try:
        thread = HNThread.objects.get(hn_id=hn_id)
    except HNThread.DoesNotExist:
        logger.error("Orchestrator: スレッドが見つかりません hn_id=%d", hn_id)
        return {"error": f"Thread not found: hn_id={hn_id}"}

    orchestrator = Orchestrator()
    result = orchestrator.investigate(thread)

    return {
        "hn_id": hn_id,
        "steps": len(result.get("steps", [])),
        "has_memory": result.get("memory_result") is not None,
        "has_detective": result.get("detective_result") is not None,
    }


@shared_task(name="hn_agent.cleanup_old_snapshots")
def cleanup_old_snapshots(days: int = 90) -> dict:
    """古いスナップショットを刈り込み.

    未調査かつ低スコアのスレッドに紐づくスナップショットを削除する。

    Args:
        days: 保持期間（日数）

    Returns:
        削除結果のサマリー
    """
    cutoff = timezone.now() - timedelta(days=days)

    # 未調査スレッドの古いスナップショットを削除
    old_snapshots = HNThreadSnapshot.objects.filter(
        thread__is_investigated=False,
        fetched_at__lt=cutoff,
    )
    deleted_count = old_snapshots.count()
    old_snapshots.delete()

    # スナップショットがなくなった未調査スレッドも削除
    orphan_threads = HNThread.objects.filter(
        is_investigated=False,
        snapshots__isnull=True,
    )
    orphan_count = orphan_threads.count()
    orphan_threads.delete()

    logger.info(
        "クリーンアップ完了: スナップショット削除=%d, スレッド削除=%d",
        deleted_count,
        orphan_count,
    )

    return {
        "snapshots_deleted": deleted_count,
        "threads_deleted": orphan_count,
    }
