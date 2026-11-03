"""HN Watcherを手動実行するmanagement command."""

from django.core.management.base import BaseCommand

from features.hn_agent.tasks import poll_front_page


class Command(BaseCommand):
    """HNフロントページのポーリングを手動実行."""

    help = (
        "HNフロントページをポーリングしてスナップショットを記録する（ポーリングのみ。"
        "トリガーされたスレッドの調査は run_hn_investigation --hn-id <hn_id> で行う）"
    )

    def handle(self, *args, **options):
        """コマンドを実行."""
        self.stdout.write("HN Watcherを実行中...")

        # Celeryを経由せず同期実行し、Orchestratorの自動起動はしない
        result = poll_front_page(auto_investigate=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"完了: {result['stories_fetched']}件取得, "
                f"新規{result['new_threads']}件, "
                f"スナップショット{result['snapshots_created']}件, "
                f"トリガー{len(result['triggered_threads'])}件"
            )
        )

        for thread in result["triggered_threads"]:
            self.stdout.write(
                self.style.WARNING(
                    f"  → [{thread['hn_id']}] {thread['title']} "
                    f"(score={thread['score']}, "
                    f"velocity={thread['score_velocity']:.1f}/h)"
                    if thread["score_velocity"] is not None
                    else f"  → [{thread['hn_id']}] {thread['title']} "
                    f"(score={thread['score']})"
                )
            )
