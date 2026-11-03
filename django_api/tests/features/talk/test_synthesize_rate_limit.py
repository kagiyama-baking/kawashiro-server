"""POST /talk/synthesize/ の回数制限（会話生成設定ごとの上限）のテスト.

LLM は呼ばない（ビューの `TalkService` を差し替える）。回数の記録先は
`tests/conftest.py` がプロセス内のキャッシュに替え、テストごとに空にする。
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.forms.models import model_to_dict
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from features.talk.models import TalkConfig
from features.talk.throttling import TalkConfigRateThrottle
from integrations.langfuse.models import LangfusePromptRef
from integrations.llm.exceptions import LLMClientError

User = get_user_model()


@pytest.fixture(autouse=True)
def synthesize_service():
    """生成を LLM なしで成功させる（呼ばれた回数を確かめられる）."""
    with patch("features.talk.views.synthesize.TalkService") as service_class:
        service = service_class.return_value
        service.synthesize.return_value = {"greeting_text": "おはようございます"}
        yield service


@pytest.fixture
def make_config(db):
    """上限を指定してプリセットを作る（limit を省くとモデルの既定値）."""
    prompt_ref = LangfusePromptRef.objects.create(
        name="talk-rate-limit",
        langfuse_prompt_name="talk-rate-limit",
        fallback_text="プロンプト",
    )

    def make(name: str = "morning", **fields) -> TalkConfig:
        return TalkConfig.objects.create(
            name=name,
            display_name=name,
            system_prompt_ref=prompt_ref,
            user_prompt_ref=prompt_ref,
            **fields,
        )

    return make


@pytest.fixture
def admin_site_client(client, superuser):
    """管理画面にログインしたクライアント."""
    client.force_login(superuser)
    return client


def _client_for(user) -> APIClient:
    token, _ = Token.objects.get_or_create(user=user)
    api_client = APIClient()
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def _synthesize(api_client, config_name: str = "morning", **body):
    return api_client.post(
        reverse("talk:synthesize"), {"config_name": config_name, **body}, format="json"
    )


def _change_limit_in_admin(admin_site_client, config: TalkConfig, limit: int) -> None:
    """管理画面の変更フォームから上限だけを替えて保存する."""
    data = {**model_to_dict(config), "synthesize_rate_limit": limit}
    response = admin_site_client.post(
        reverse("admin:talk_talkconfig_change", args=[config.pk]), data
    )
    assert response.status_code == status.HTTP_302_FOUND
    config.refresh_from_db()
    assert config.synthesize_rate_limit == limit


@pytest.mark.django_db
class TestSynthesizeRateLimit:
    """プリセットの上限を超えると 429 を返す."""

    def test_synthesize_over_limit_returns_429_with_retry_after(
        self, authenticated_client, make_config, synthesize_service
    ):
        """上限 2 のプリセットでは 3 回目が 429 になり、生成はしない."""
        make_config(synthesize_rate_limit=2)

        first, second, third = (_synthesize(authenticated_client) for _ in range(3))

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert 0 < int(third["Retry-After"]) <= 60
        assert synthesize_service.synthesize.call_count == 2

    def test_synthesize_with_default_limit_allows_10_per_minute(
        self, authenticated_client, make_config
    ):
        """上限を指定しないプリセットは 1 分に 10 回まで."""
        make_config()

        codes = [_synthesize(authenticated_client).status_code for _ in range(11)]

        assert codes == [status.HTTP_200_OK] * 10 + [status.HTTP_429_TOO_MANY_REQUESTS]

    def test_synthesize_limit_resets_after_one_minute(
        self, authenticated_client, make_config
    ):
        """回数は直近 1 分で数え、1 分たてば再び生成できる."""
        make_config(synthesize_rate_limit=1)

        with patch.object(TalkConfigRateThrottle, "timer") as timer:
            timer.return_value = 1_000.0
            assert _synthesize(authenticated_client).status_code == status.HTTP_200_OK
            timer.return_value = 1_059.0
            blocked = _synthesize(authenticated_client)
            timer.return_value = 1_060.0
            allowed = _synthesize(authenticated_client)

        assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert blocked["Retry-After"] == "1"
        assert allowed.status_code == status.HTTP_200_OK

    def test_synthesize_with_zero_limit_always_returns_429(
        self, authenticated_client, make_config, synthesize_service
    ):
        """検証を通さずに 0 が入っても落ちず、常に 429 にする（生成はしない）."""
        config = make_config()
        TalkConfig.objects.filter(pk=config.pk).update(synthesize_rate_limit=0)

        response = _synthesize(authenticated_client)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response["Retry-After"] == "60"
        synthesize_service.synthesize.assert_not_called()

    def test_synthesize_failed_generation_is_counted(
        self, authenticated_client, make_config, synthesize_service
    ):
        """生成に失敗しても 1 回と数える（LLM は呼んでいる）."""
        make_config(synthesize_rate_limit=1)
        synthesize_service.synthesize.side_effect = LLMClientError("upstream error")

        failed = _synthesize(authenticated_client)
        blocked = _synthesize(authenticated_client)

        assert failed.status_code == status.HTTP_502_BAD_GATEWAY
        assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
class TestSynthesizeRateLimitScope:
    """ユーザーとプリセットの組ごとに数える."""

    def test_synthesize_limit_counts_each_preset_separately(
        self, authenticated_client, make_config
    ):
        """あるプリセットが上限に達しても、別のプリセットは生成できる."""
        make_config("morning", synthesize_rate_limit=1)
        make_config("evening", synthesize_rate_limit=1)

        assert _synthesize(authenticated_client, "morning").status_code == 200
        assert _synthesize(authenticated_client, "morning").status_code == 429
        assert _synthesize(authenticated_client, "evening").status_code == 200

    def test_synthesize_limit_counts_each_user_separately(
        self, authenticated_client, make_config
    ):
        """あるユーザーが上限に達しても、別のユーザーは生成できる."""
        make_config(synthesize_rate_limit=1)
        other_client = _client_for(
            User.objects.create_user(email="other@example.com", password="otherpass1")
        )

        assert _synthesize(authenticated_client).status_code == 200
        assert _synthesize(authenticated_client).status_code == 429
        assert _synthesize(other_client).status_code == 200

    def test_synthesize_config_name_with_spaces_counts_as_same_preset(
        self, authenticated_client, make_config
    ):
        """ビューと同じく前後の空白を除いて数える（空白を足しても回避できない）."""
        make_config(synthesize_rate_limit=1)

        assert _synthesize(authenticated_client, "morning").status_code == 200
        assert _synthesize(authenticated_client, " morning ").status_code == 429


@pytest.mark.django_db
class TestSynthesizeRateLimitChangedInAdmin:
    """管理画面で上限を変えると、次のリクエストから効く."""

    def test_synthesize_raised_limit_applies_to_next_request(
        self, authenticated_client, admin_site_client, make_config
    ):
        """上限を上げれば、上限に達していても続けて生成できる."""
        config = make_config(synthesize_rate_limit=1)
        assert _synthesize(authenticated_client).status_code == 200
        assert _synthesize(authenticated_client).status_code == 429

        _change_limit_in_admin(admin_site_client, config, 2)

        assert _synthesize(authenticated_client).status_code == 200
        assert _synthesize(authenticated_client).status_code == 429

    def test_synthesize_lowered_limit_applies_to_next_request(
        self, authenticated_client, admin_site_client, make_config
    ):
        """上限を直近の回数より下げると、次は 429 になり Retry-After も付く."""
        config = make_config(synthesize_rate_limit=3)
        assert _synthesize(authenticated_client).status_code == 200
        assert _synthesize(authenticated_client).status_code == 200

        _change_limit_in_admin(admin_site_client, config, 1)
        blocked = _synthesize(authenticated_client)

        assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert 0 < int(blocked["Retry-After"]) <= 60


@pytest.mark.django_db
class TestSynthesizeRateLimitSkipped:
    """プリセットが決まらないリクエストは数えない（ビューが 400 / 404 を返す）."""

    def test_synthesize_unknown_config_returns_404_without_limit(
        self, authenticated_client
    ):
        """存在しない設定は、既定の上限を超えて送っても 404 のまま."""
        codes = [
            _synthesize(authenticated_client, "nonexistent").status_code
            for _ in range(11)
        ]

        assert codes == [status.HTTP_404_NOT_FOUND] * 11

    @pytest.mark.parametrize(
        ("body", "content_type"),
        [
            pytest.param({}, None, id="missing_config_name"),
            pytest.param(
                {"config_name": "morning", "user_prompt": "x" * 4001},
                None,
                id="too_long_user_prompt",
            ),
            pytest.param([{"config_name": "morning"}], None, id="not_an_object"),
            pytest.param("{broken", "application/json", id="malformed_json"),
        ],
    )
    def test_synthesize_invalid_body_returns_400_and_is_not_counted(
        self, authenticated_client, make_config, body, content_type
    ):
        """不正な本文は上限を超えて送っても 400 のままで、回数にも入らない."""
        make_config(synthesize_rate_limit=1)
        url = reverse("talk:synthesize")
        encoding = (
            {"format": "json"}
            if content_type is None
            else {"content_type": content_type}
        )

        codes = [
            authenticated_client.post(url, body, **encoding).status_code
            for _ in range(2)
        ]

        assert codes == [status.HTTP_400_BAD_REQUEST] * 2
        assert _synthesize(authenticated_client).status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestTalkConfigRateThrottleCacheKey:
    """記録のキー（ユーザーとプリセットの組）."""

    @pytest.fixture
    def throttle(self):
        throttle = TalkConfigRateThrottle()
        throttle.config_pk = 3
        return throttle

    @staticmethod
    def _request(user) -> Request:
        django_request = APIRequestFactory().post(
            "/talk/synthesize/", {"config_name": "morning"}, REMOTE_ADDR="198.51.100.7"
        )
        request = Request(django_request)
        request.user = user
        return request

    def test_cache_key_combines_user_and_preset(self, throttle, regular_user):
        """認証済みならユーザーの pk とプリセットの pk で数える."""
        key = throttle.get_cache_key(self._request(regular_user), view=None)

        assert key == f"throttle_talk_synthesize_{regular_user.pk}_3"

    def test_cache_key_for_anonymous_uses_client_address(self, throttle):
        """未認証（ビューは通さないが）なら接続元とプリセットの pk で数える."""
        key = throttle.get_cache_key(self._request(AnonymousUser()), view=None)

        assert key == "throttle_talk_synthesize_198.51.100.7_3"


class TestSynthesizeRateLimitSchema:
    """OpenAPI スキーマ."""

    def test_synthesize_schema_documents_429(self):
        """回数制限の 429 がスキーマに載る."""
        schema = SchemaGenerator().get_schema(request=None, public=True)

        responses = schema["paths"]["/talk/synthesize/"]["post"]["responses"]
        assert "429" in responses
