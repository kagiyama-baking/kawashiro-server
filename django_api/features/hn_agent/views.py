"""HN Agent APIビュー."""

import logging

from drf_spectacular.utils import extend_schema
from langfuse import observe
from rest_framework import authentication, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import HNThread
from .serializers import (
    InvestigateRequestSerializer,
    InvestigateResponseSerializer,
    ThreadListSerializer,
    WatcherResponseSerializer,
)

logger = logging.getLogger(__name__)


MAX_SYNC_INVESTIGATIONS = 3


class RunAllView(APIView):
    """Watcher → Orchestrator を一括実行するAPI."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAdminUser,)

    @extend_schema(
        tags=["hn-agent"],
        summary="エージェント一括実行",
        description=(
            "HNフロントページをポーリングし、閾値超えスレッドに対して"
            "Orchestratorを同期的に順次実行する。テスト・デバッグ用。"
        ),
    )
    def post(self, request):
        """Watcher + Orchestrator を同期実行."""
        return Response(_run_all_impl())


class WatcherRunView(APIView):
    """HN Watcherを手動実行するAPI."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAdminUser,)

    @extend_schema(
        tags=["hn-agent"],
        summary="HN Watcherを実行",
        description="HNフロントページをポーリングし、スナップショットを記録する。閾値超えスレッドのOrchestrator起動はスキップされる。",
        responses={200: WatcherResponseSerializer},
    )
    def post(self, request):
        """Watcherを同期実行."""
        from .tasks import poll_front_page

        result = poll_front_page(auto_investigate=False)
        return Response(result, status=status.HTTP_200_OK)


class InvestigateView(APIView):
    """HNスレッドの調査を手動実行するAPI."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAdminUser,)

    @extend_schema(
        tags=["hn-agent"],
        summary="HNスレッドを調査",
        description="指定したHN IDのスレッドに対してOrchestratorを実行し、調査結果を返す。",
        request=InvestigateRequestSerializer,
        responses={200: InvestigateResponseSerializer},
    )
    def post(self, request):
        """Orchestratorを同期実行."""
        serializer = InvestigateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        hn_id = serializer.validated_data["hn_id"]
        skip_notify = serializer.validated_data["skip_notify"]

        try:
            thread = HNThread.objects.get(hn_id=hn_id)
        except HNThread.DoesNotExist:
            return Response(
                {
                    "error": f"HNスレッド hn_id={hn_id} が見つかりません。先にWatcherを実行してください。"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        result = _investigate_impl(thread, skip_notify)
        return Response(result, status=status.HTTP_200_OK)


class ThreadListView(APIView):
    """HNスレッド一覧API."""

    authentication_classes = (authentication.TokenAuthentication,)
    permission_classes = (permissions.IsAdminUser,)

    @extend_schema(
        tags=["hn-agent"],
        summary="HNスレッド一覧",
        description="監視中のHNスレッド一覧を最新スナップショット付きで返す。",
        responses={200: ThreadListSerializer(many=True)},
    )
    def get(self, request):
        """スレッド一覧を取得."""
        threads = HNThread.objects.all()[:50]

        data = []
        for thread in threads:
            snapshot = thread.latest_snapshot
            data.append(
                {
                    "hn_id": thread.hn_id,
                    "title": thread.title,
                    "url": thread.url,
                    "author": thread.author,
                    "is_investigated": thread.is_investigated,
                    "first_seen": thread.first_seen,
                    "latest_score": snapshot.score if snapshot else None,
                    "latest_num_comments": snapshot.num_comments if snapshot else None,
                }
            )

        serializer = ThreadListSerializer(data, many=True)
        return Response(serializer.data)


# ============================================================
# Langfuseトレース付きの実装関数
# APIビューのエントリーポイントとして@observeを適用し、
# 配下の全LLM呼び出しを1トレースに集約する。
# ============================================================


@observe(name="hn-agent/run-all")
def _run_all_impl() -> dict:
    """run-allの実装（Langfuseトレース対応）."""
    from .orchestrator import Orchestrator
    from .tasks import poll_front_page

    watcher_result = poll_front_page(auto_investigate=False)
    triggered = watcher_result.get("triggered_threads", [])
    skipped_count = max(0, len(triggered) - MAX_SYNC_INVESTIGATIONS)
    triggered = triggered[:MAX_SYNC_INVESTIGATIONS]

    orchestrator = Orchestrator()
    investigations = []

    investigated_ids = set()
    for triggered_thread in triggered:
        hn_id = triggered_thread["hn_id"]
        if hn_id in investigated_ids:
            continue

        try:
            thread = HNThread.objects.get(hn_id=hn_id)
        except HNThread.DoesNotExist:
            continue

        if thread.is_investigated:
            continue

        result = orchestrator.investigate(thread)
        investigated_ids.add(hn_id)
        investigations.append(
            {
                "hn_id": hn_id,
                "title": triggered_thread["title"],
                "steps": len(result.get("steps", [])),
                "final_summary": result.get("final_summary", "")[:200],
            }
        )

    _flush_langfuse()

    return {
        "watcher": {
            "stories_fetched": watcher_result["stories_fetched"],
            "new_threads": watcher_result["new_threads"],
            "triggered_count": len(triggered) + skipped_count,
            "investigated_count": len(investigations),
            "skipped_count": skipped_count,
        },
        "investigations": investigations,
    }


@observe(name="hn-agent/investigate")
def _investigate_impl(thread: HNThread, skip_notify: bool) -> dict:
    """investigateの実装（Langfuseトレース対応）."""
    from .orchestrator import Orchestrator
    from .reporter import Reporter

    reporter = None if skip_notify else Reporter()
    orchestrator = Orchestrator(reporter=reporter)
    result = orchestrator.investigate(thread)
    _flush_langfuse()
    return result


def _flush_langfuse() -> None:
    """Langfuseのトレースデータを確実に送信."""
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        pass
