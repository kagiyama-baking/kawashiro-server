"""HN調査を手動実行するmanagement command."""

from django.core.management.base import BaseCommand, CommandError

from features.hn_agent.models import HNThread
from features.hn_agent.orchestrator import Orchestrator


class Command(BaseCommand):
    """指定したHNスレッドの調査を手動実行."""

    help = "HNスレッドの調査をOrchestratorで手動実行する"

    def add_arguments(self, parser):
        """コマンド引数を追加."""
        parser.add_argument(
            "--hn-id",
            type=int,
            required=True,
            help="調査対象のHacker News ID",
        )
        parser.add_argument(
            "--skip-notify",
            action="store_true",
            default=False,
            help="Slack通知をスキップする",
        )

    def handle(self, *args, **options):
        """コマンドを実行."""
        hn_id = options["hn_id"]

        try:
            thread = HNThread.objects.get(hn_id=hn_id)
        except HNThread.DoesNotExist:
            raise CommandError(f"HNスレッド hn_id={hn_id} が見つかりません") from None

        self.stdout.write(f"Orchestrator開始: [{thread.hn_id}] {thread.title}")

        from features.hn_agent.reporter import Reporter

        reporter = None if options["skip_notify"] else Reporter()
        orchestrator = Orchestrator(reporter=reporter)
        result = orchestrator.investigate(thread)

        self.stdout.write(f"  ステップ数: {len(result['steps'])}")
        for step in result["steps"]:
            self.stdout.write(f"  → Step {step['step']}: {step['action']}")

        if result.get("final_summary"):
            self.stdout.write(self.style.SUCCESS("\n=== 最終サマリー ==="))
            self.stdout.write(result["final_summary"])

        self.stdout.write(self.style.SUCCESS("\n調査完了"))
