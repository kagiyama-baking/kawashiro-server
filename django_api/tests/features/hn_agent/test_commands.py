"""HN Agent 管理コマンドのテスト."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command


@pytest.mark.django_db
@pytest.mark.integration
class TestRunHNInvestigationCommand:
    """run_hn_investigation のテスト."""

    def _run(self, *args: str) -> str:
        out = StringIO()
        call_command("run_hn_investigation", *args, stdout=out)
        return out.getvalue()

    def test_command_with_skip_notify_does_not_create_reporter(
        self, investigation_thread, reporter_class
    ):
        """--skip-notify なら結果があっても Reporter を作らない（Slack へ送らない）."""
        output = self._run("--hn-id", str(investigation_thread.hn_id), "--skip-notify")

        assert "調査完了" in output
        investigation_thread.refresh_from_db()
        assert investigation_thread.is_investigated is True
        reporter_class.assert_not_called()

    def test_command_without_skip_notify_sends_report(
        self, investigation_thread, reporter_class
    ):
        """--skip-notify がなければ調査結果を Slack へ送る."""
        self._run("--hn-id", str(investigation_thread.hn_id))

        reporter_class.assert_called_once_with()
        reporter_class.return_value.report_detective.assert_called_once()

    def test_command_with_unknown_hn_id_raises_command_error(self):
        """存在しないスレッドはエラーにする."""
        with pytest.raises(CommandError, match="hn_id=1 が見つかりません"):
            self._run("--hn-id", "1")


@pytest.mark.unit
class TestRunHNWatcherCommand:
    """run_hn_watcher のテスト."""

    @pytest.fixture
    def poll_front_page(self):
        """ポーリングを差し替える（HN へは出ない）."""
        with patch(
            "features.hn_agent.management.commands.run_hn_watcher.poll_front_page",
            return_value={
                "stories_fetched": 2,
                "new_threads": 1,
                "snapshots_created": 2,
                "triggered_threads": [],
            },
        ) as poll:
            yield poll

    def test_command_polls_without_investigation(self, poll_front_page):
        """ポーリングだけを行い、トリガーされたスレッドの調査は実行しない."""
        out = StringIO()

        call_command("run_hn_watcher", stdout=out)

        poll_front_page.assert_called_once_with(auto_investigate=False)
        assert "完了: 2件取得" in out.getvalue()

    def test_command_with_sync_option_raises_command_error(self, poll_front_page):
        """--sync は削除した（常にポーリングのみ）ので、渡すとエラーにする."""
        with pytest.raises(CommandError, match="unrecognized arguments: --sync"):
            call_command("run_hn_watcher", "--sync", stdout=StringIO())

        poll_front_page.assert_not_called()
