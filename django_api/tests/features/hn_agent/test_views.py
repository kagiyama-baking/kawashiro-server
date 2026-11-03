"""HN Agent API ビューのテスト（Slack 通知の有無）."""

from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

pytestmark = [pytest.mark.django_db, pytest.mark.api]


class TestInvestigateView:
    """POST /hn-agent/investigate/ のテスト."""

    def _post(self, client, data: dict):
        return client.post(reverse("hn_agent:investigate"), data, format="json")

    def test_investigate_with_skip_notify_does_not_create_reporter(
        self, superuser_client, investigation_thread, reporter_class
    ):
        """skip_notify=true なら結果があっても Reporter を作らない（Slack へ送らない）."""
        response = self._post(
            superuser_client, {"hn_id": investigation_thread.hn_id, "skip_notify": True}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["detective_result"] is not None
        reporter_class.assert_not_called()

    def test_investigate_without_skip_notify_field_does_not_create_reporter(
        self, superuser_client, investigation_thread, reporter_class
    ):
        """skip_notify の既定は true なので、省略しても Slack へ送らない."""
        response = self._post(superuser_client, {"hn_id": investigation_thread.hn_id})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["detective_result"] is not None
        reporter_class.assert_not_called()

    def test_investigate_with_skip_notify_false_sends_report(
        self, superuser_client, investigation_thread, reporter_class
    ):
        """skip_notify=false なら調査結果を Slack へ送る."""
        response = self._post(
            superuser_client,
            {"hn_id": investigation_thread.hn_id, "skip_notify": False},
        )

        assert response.status_code == status.HTTP_200_OK
        reporter_class.assert_called_once_with()
        reporter_class.return_value.report_detective.assert_called_once()


class TestRunAllView:
    """POST /hn-agent/run-all/ のテスト."""

    def test_run_all_sends_report(
        self, superuser_client, investigation_thread, reporter_class
    ):
        """一括実行は従来どおり調査結果を Slack へ送る."""
        watcher_result = {
            "stories_fetched": 1,
            "new_threads": 0,
            "triggered_threads": [
                {
                    "hn_id": investigation_thread.hn_id,
                    "title": investigation_thread.title,
                }
            ],
        }

        with patch(
            "features.hn_agent.tasks.poll_front_page", return_value=watcher_result
        ):
            response = superuser_client.post(reverse("hn_agent:run-all"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["watcher"]["investigated_count"] == 1
        reporter_class.return_value.report_detective.assert_called_once()
