"""Companion の実行 API の回数制限（CompanionRateThrottle）のテスト.

上限は有効な Companion 設定の `rate_limit`（1 分あたり）で、ユーザーごとに数える。
実行サービスはビューが参照する名前で差し替える（LLM は呼ばない）。回数の記録先は
`tests/conftest.py` がプロセス内のキャッシュに替え、テストごとに空にする。
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.companion.models import CompanionConfig
from features.companion.services import CompanionReply
from features.companion.throttling import CompanionRateThrottle
from integrations.llm.exceptions import LLMClientError
from tests.fixtures.factories import CompanionConfigFactory

pytestmark = [pytest.mark.api, pytest.mark.django_db]

REPLY = CompanionReply(text="おはようございます", skill=None, audio=None)


def _patch_service():
    """ビューが呼ぶ実行サービスを、REPLY を返すものに差し替える."""
    return patch(
        "features.companion.views.run_companion", autospec=True, return_value=REPLY
    )


@pytest.fixture
def run_companion():
    """実行サービスを差し替える（呼ばれた回数を確かめられる）."""
    with _patch_service() as mocked:
        yield mocked


def _post(client, body=None):
    return client.post(
        reverse("companion:run"), body or {"prompt": "おはよう"}, format="json"
    )


def _client_for(user) -> APIClient:
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class TestCompanionRateLimit:
    """有効な設定の上限を超えると 429 を返す."""

    def test_run_over_rate_limit_returns_429_with_retry_after(
        self, authenticated_client, run_companion
    ):
        """上限 2 なら 3 回目が 429 で、実行しない（無効な設定の上限は使わない）."""
        CompanionConfigFactory(is_active=False, rate_limit=5)
        CompanionConfigFactory(is_active=True, rate_limit=2)

        first, second, third = (_post(authenticated_client) for _ in range(3))

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert 0 < int(third["Retry-After"]) <= 60
        assert run_companion.call_count == 2

    def test_run_limit_resets_after_one_minute(
        self, authenticated_client, run_companion
    ):
        """回数は直近 1 分で数え、1 分たてば再び実行できる."""
        CompanionConfigFactory(is_active=True, rate_limit=1)

        with patch.object(CompanionRateThrottle, "timer") as timer:
            timer.return_value = 1_000.0
            assert _post(authenticated_client).status_code == status.HTTP_200_OK
            timer.return_value = 1_059.0
            blocked = _post(authenticated_client)
            timer.return_value = 1_060.0
            allowed = _post(authenticated_client)

        assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert blocked["Retry-After"] == "1"
        assert allowed.status_code == status.HTTP_200_OK

    def test_run_failed_generation_is_counted(
        self, authenticated_client, run_companion
    ):
        """生成に失敗しても 1 回と数える."""
        CompanionConfigFactory(is_active=True, rate_limit=1)
        run_companion.side_effect = LLMClientError("upstream error")

        failed = _post(authenticated_client)
        blocked = _post(authenticated_client)

        assert failed.status_code == status.HTTP_502_BAD_GATEWAY
        assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_run_invalid_body_is_counted(self, authenticated_client, run_companion):
        """入力が不正な（400 の）リクエストも 1 回と数える."""
        CompanionConfigFactory(is_active=True, rate_limit=1)

        invalid = _post(authenticated_client, {"prompt": ""})
        blocked = _post(authenticated_client)

        assert invalid.status_code == status.HTTP_400_BAD_REQUEST
        assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        run_companion.assert_not_called()

    def test_run_with_zero_limit_always_returns_429(
        self, authenticated_client, run_companion
    ):
        """検証を通さずに 0 が入っても落ちず、常に 429 にする（実行しない）."""
        config = CompanionConfigFactory(is_active=True)
        CompanionConfig.objects.filter(pk=config.pk).update(rate_limit=0)

        response = _post(authenticated_client)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response["Retry-After"] == "60"
        run_companion.assert_not_called()


class TestCompanionRateLimitScope:
    """ユーザーごとに数える."""

    def test_run_limit_counts_each_user_separately(
        self, authenticated_client, run_companion
    ):
        """あるユーザーが上限に達しても、別のユーザーは実行できる."""
        CompanionConfigFactory(is_active=True, rate_limit=1)
        other_client = _client_for(
            get_user_model().objects.create_user(
                email="other@example.com", password="otherpass1"
            )
        )

        assert _post(authenticated_client).status_code == status.HTTP_200_OK
        assert _post(authenticated_client).status_code == 429
        assert _post(other_client).status_code == status.HTTP_200_OK


class TestCompanionRateLimitChanged:
    """上限を変えると、次のリクエストから効く（毎回 DB から読む）."""

    def test_run_raised_limit_applies_to_next_request(
        self, authenticated_client, run_companion
    ):
        """上限を上げれば、上限に達していても続けて実行できる."""
        config = CompanionConfigFactory(is_active=True, rate_limit=1)
        assert _post(authenticated_client).status_code == status.HTTP_200_OK
        assert _post(authenticated_client).status_code == 429

        config.rate_limit = 2
        config.save()

        assert _post(authenticated_client).status_code == status.HTTP_200_OK
        assert _post(authenticated_client).status_code == 429

    def test_run_lowered_limit_returns_429_with_retry_after(
        self, authenticated_client, run_companion
    ):
        """直近の回数より下げると次は 429 になり、通るまでの秒数が付く.

        上限 1 なら、最も新しい記録（1_020）が 1 分の窓から抜ける 1_080 に通る。
        """
        config = CompanionConfigFactory(is_active=True, rate_limit=3)

        with patch.object(CompanionRateThrottle, "timer") as timer:
            for now in (1_000.0, 1_010.0, 1_020.0):
                timer.return_value = now
                assert _post(authenticated_client).status_code == status.HTTP_200_OK
            config.rate_limit = 1
            config.save()
            timer.return_value = 1_030.0
            blocked = _post(authenticated_client)
            timer.return_value = 1_079.0
            still_blocked = _post(authenticated_client)
            timer.return_value = 1_080.0
            allowed = _post(authenticated_client)

        assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert blocked["Retry-After"] == "50"
        assert still_blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert still_blocked["Retry-After"] == "1"
        assert allowed.status_code == status.HTTP_200_OK


class TestCompanionRateLimitWithoutActiveConfig:
    """有効な設定がなければ数えない（ビューが 503 を返す）."""

    def test_run_without_active_config_returns_503_and_is_not_counted(
        self, authenticated_client
    ):
        """何度送っても 503 のままで、有効にした後の 1 回目は上限 1 でも通る.

        実行サービスは差し替えないので、503 は本物の run_companion が返す。
        """
        config = CompanionConfigFactory(is_active=False, rate_limit=1)

        codes = [_post(authenticated_client).status_code for _ in range(12)]

        assert codes == [status.HTTP_503_SERVICE_UNAVAILABLE] * 12
        config.is_active = True
        config.save()
        with _patch_service():
            assert _post(authenticated_client).status_code == status.HTTP_200_OK
            assert _post(authenticated_client).status_code == 429
