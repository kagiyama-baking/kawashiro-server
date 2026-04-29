"""HN Agent Watcherタスクのテスト."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from features.hn_agent.models import HNThread, HNThreadSnapshot
from features.hn_agent.tasks import (
    _calculate_comment_velocity,
    _calculate_score_velocity,
    cleanup_old_snapshots,
    poll_front_page,
)
from integrations.hn.client import HNStory

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample_stories():
    """テスト用HNストーリーリスト."""
    return [
        HNStory(
            hn_id=100,
            title="High Score Story",
            url="https://example.com/1",
            author="user1",
            score=200,
            num_comments=50,
            created_at="2026-04-01T12:00:00.000Z",
        ),
        HNStory(
            hn_id=101,
            title="Low Score Story",
            url="https://example.com/2",
            author="user2",
            score=10,
            num_comments=3,
            created_at="2026-04-01T11:00:00.000Z",
        ),
    ]


@pytest.mark.integration
@patch("features.hn_agent.tasks.run_orchestrator.delay")
class TestPollFrontPage:
    """poll_front_pageタスクのテスト."""

    @patch("features.hn_agent.tasks.HNAlgoliaClient")
    def test_poll_front_page_creates_threads_and_snapshots(
        self, mock_client_class, _mock_delay, sample_stories
    ):
        """新規スレッドとスナップショットを作成する."""
        mock_client_class.return_value.get_front_page_stories.return_value = (
            sample_stories
        )

        result = poll_front_page()

        assert result["stories_fetched"] == 2
        assert result["new_threads"] == 2
        assert result["snapshots_created"] == 2
        assert HNThread.objects.count() == 2
        assert HNThreadSnapshot.objects.count() == 2

    @patch("features.hn_agent.tasks.HNAlgoliaClient")
    def test_poll_front_page_uses_configured_limit(
        self, mock_client_class, _mock_delay, hn_agent_config
    ):
        """HNAgentConfig.front_page_limit が Algolia 呼び出しに渡される."""
        hn_agent_config.front_page_limit = 90
        hn_agent_config.save()

        mock_client_class.return_value.get_front_page_stories.return_value = []

        poll_front_page()

        call_kwargs = (
            mock_client_class.return_value.get_front_page_stories.call_args.kwargs
        )
        assert call_kwargs["hits_per_page"] == 90

    @patch("features.hn_agent.tasks.HNAlgoliaClient")
    def test_poll_front_page_updates_existing_thread(
        self, mock_client_class, _mock_delay, sample_stories
    ):
        """既存スレッドはスナップショットのみ追加する."""
        HNThread.objects.create(
            hn_id=100,
            title="High Score Story",
            url="https://example.com/1",
            author="user1",
        )

        mock_client_class.return_value.get_front_page_stories.return_value = (
            sample_stories
        )

        result = poll_front_page()

        assert result["new_threads"] == 1  # 101のみ新規
        assert result["snapshots_created"] == 2
        assert HNThread.objects.count() == 2

    @patch("features.hn_agent.tasks._get_score_threshold", return_value=100)
    @patch("features.hn_agent.tasks.HNAlgoliaClient")
    def test_poll_front_page_triggers_on_high_score(
        self, mock_client_class, _mock_threshold, _mock_delay, sample_stories
    ):
        """スコア閾値を超えたスレッドがトリガーされる."""
        mock_client_class.return_value.get_front_page_stories.return_value = (
            sample_stories
        )

        result = poll_front_page()

        triggered_ids = [t["hn_id"] for t in result["triggered_threads"]]
        assert 100 in triggered_ids  # score=200 > threshold=100
        assert 101 not in triggered_ids  # score=10 < threshold=100

    @patch("features.hn_agent.tasks._get_score_threshold", return_value=100)
    @patch("features.hn_agent.tasks.HNAlgoliaClient")
    def test_poll_front_page_skips_already_investigated(
        self, mock_client_class, _mock_threshold, _mock_delay, sample_stories
    ):
        """調査済みスレッドはスコア閾値でトリガーされない."""
        HNThread.objects.create(
            hn_id=100,
            title="High Score Story",
            url="https://example.com/1",
            author="user1",
            is_investigated=True,
        )

        mock_client_class.return_value.get_front_page_stories.return_value = (
            sample_stories
        )

        result = poll_front_page()

        triggered_ids = [t["hn_id"] for t in result["triggered_threads"]]
        assert 100 not in triggered_ids

    @patch("features.hn_agent.tasks.HNAlgoliaClient")
    def test_poll_front_page_empty_stories(self, mock_client_class, _mock_delay):
        """空のストーリーリストを正しく処理する."""
        mock_client_class.return_value.get_front_page_stories.return_value = []

        result = poll_front_page()

        assert result["stories_fetched"] == 0
        assert result["new_threads"] == 0
        assert result["snapshots_created"] == 0
        assert result["triggered_threads"] == []


@pytest.mark.integration
class TestCalculateVelocity:
    """スコア・コメント速度計算のテスト."""

    def test_calculate_score_velocity_with_previous_snapshot(self):
        """前回スナップショットがある場合にスコア速度を計算する."""
        thread = HNThread.objects.create(
            hn_id=200,
            title="Test",
        )
        # 1時間前のスナップショット
        snapshot = HNThreadSnapshot.objects.create(
            thread=thread,
            score=50,
            num_comments=10,
        )
        snapshot.fetched_at = timezone.now() - timedelta(hours=1)
        HNThreadSnapshot.objects.filter(pk=snapshot.pk).update(
            fetched_at=snapshot.fetched_at
        )
        snapshot.refresh_from_db()

        velocity = _calculate_score_velocity(thread, 150)

        assert velocity is not None
        assert velocity == pytest.approx(100.0, rel=0.1)

    def test_calculate_score_velocity_without_previous_snapshot(self):
        """前回スナップショットがない場合はNoneを返す."""
        thread = HNThread.objects.create(
            hn_id=201,
            title="Test",
        )

        velocity = _calculate_score_velocity(thread, 100)

        assert velocity is None

    def test_calculate_comment_velocity_with_previous_snapshot(self):
        """前回スナップショットがある場合にコメント速度を計算する."""
        thread = HNThread.objects.create(
            hn_id=202,
            title="Test",
        )
        snapshot = HNThreadSnapshot.objects.create(
            thread=thread,
            score=50,
            num_comments=10,
        )
        snapshot.fetched_at = timezone.now() - timedelta(hours=2)
        HNThreadSnapshot.objects.filter(pk=snapshot.pk).update(
            fetched_at=snapshot.fetched_at
        )
        snapshot.refresh_from_db()

        velocity = _calculate_comment_velocity(thread, 30)

        assert velocity is not None
        assert velocity == pytest.approx(10.0, rel=0.1)


@pytest.mark.integration
class TestCleanupOldSnapshots:
    """cleanup_old_snapshotsタスクのテスト."""

    def test_cleanup_deletes_old_uninvestigated_snapshots(self):
        """古い未調査スナップショットを削除する."""
        thread = HNThread.objects.create(
            hn_id=300,
            title="Old Thread",
            is_investigated=False,
        )
        old_snapshot = HNThreadSnapshot.objects.create(
            thread=thread,
            score=10,
            num_comments=2,
        )
        HNThreadSnapshot.objects.filter(pk=old_snapshot.pk).update(
            fetched_at=timezone.now() - timedelta(days=100)
        )

        result = cleanup_old_snapshots(days=90)

        assert result["snapshots_deleted"] == 1
        assert result["threads_deleted"] == 1

    def test_cleanup_preserves_investigated_thread_snapshots(self):
        """調査済みスレッドのスナップショットは保持する."""
        thread = HNThread.objects.create(
            hn_id=301,
            title="Investigated Thread",
            is_investigated=True,
        )
        snapshot = HNThreadSnapshot.objects.create(
            thread=thread,
            score=500,
            num_comments=200,
        )
        HNThreadSnapshot.objects.filter(pk=snapshot.pk).update(
            fetched_at=timezone.now() - timedelta(days=100)
        )

        result = cleanup_old_snapshots(days=90)

        assert result["snapshots_deleted"] == 0
        assert HNThreadSnapshot.objects.filter(thread=thread).exists()

    def test_cleanup_preserves_recent_snapshots(self):
        """期間内のスナップショットは保持する."""
        thread = HNThread.objects.create(
            hn_id=302,
            title="Recent Thread",
            is_investigated=False,
        )
        HNThreadSnapshot.objects.create(
            thread=thread,
            score=20,
            num_comments=5,
        )

        result = cleanup_old_snapshots(days=90)

        assert result["snapshots_deleted"] == 0
        assert HNThreadSnapshot.objects.filter(thread=thread).exists()


@pytest.mark.integration
class TestHNThreadModel:
    """HNThreadモデルのテスト."""

    def test_create_thread(self):
        """スレッドを作成できる."""
        thread = HNThread.objects.create(
            hn_id=400,
            title="Test Thread",
            url="https://example.com",
            author="test",
        )

        assert thread.hn_id == 400
        assert thread.is_investigated is False
        assert thread.first_seen is not None

    def test_thread_str(self):
        """__str__が正しいフォーマットを返す."""
        thread = HNThread.objects.create(
            hn_id=401,
            title="My Title",
        )

        assert str(thread) == "[401] My Title"

    def test_latest_snapshot_returns_most_recent(self):
        """latest_snapshotが最新のスナップショットを返す."""
        thread = HNThread.objects.create(
            hn_id=402,
            title="Test",
        )
        HNThreadSnapshot.objects.create(thread=thread, score=10, num_comments=1)
        latest = HNThreadSnapshot.objects.create(
            thread=thread, score=50, num_comments=10
        )

        assert thread.latest_snapshot.pk == latest.pk

    def test_latest_snapshot_returns_none_when_empty(self):
        """スナップショットがない場合はNoneを返す."""
        thread = HNThread.objects.create(
            hn_id=403,
            title="Test",
        )

        assert thread.latest_snapshot is None

    def test_hn_id_unique_constraint(self):
        """hn_idのユニーク制約が機能する."""
        from django.db import IntegrityError

        HNThread.objects.create(hn_id=404, title="First")

        with pytest.raises(IntegrityError):
            HNThread.objects.create(hn_id=404, title="Duplicate")
