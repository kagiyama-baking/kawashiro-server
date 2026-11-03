"""キャッシュ（レート制限の記録先）の設定のテスト."""

import runpy
from pathlib import Path

import pytest
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache

from django_api.settings import cache_url_from_broker

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "django_api" / "settings.py"


def _load_settings(monkeypatch, **env: str | None) -> dict:
    """環境変数を替えて settings.py を読み直し、設定の値を返す.

    稼働中の Django の設定は替えない。開発者の `.env` に左右されないよう、
    `load_dotenv` は止める。値が None の変数は未設定にする。
    """
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    for name, value in env.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return runpy.run_path(str(SETTINGS_PATH))


@pytest.mark.unit
class TestCacheUrlFromBroker:
    """Celery のブローカー URL からキャッシュの接続先を作る."""

    @pytest.mark.parametrize(
        ("broker_url", "expected"),
        [
            pytest.param("redis://redis:6379/0", "redis://redis:6379/1", id="db0"),
            pytest.param("redis://redis:6379", "redis://redis:6379/1", id="no_db"),
            pytest.param("redis://redis:6379/", "redis://redis:6379/1", id="slash"),
            pytest.param("redis://redis:6379/15", "redis://redis:6379/1", id="db15"),
            pytest.param(
                "redis://user:p%40ss@redis:6379/0",
                "redis://user:p%40ss@redis:6379/1",
                id="credentials",
            ),
            pytest.param(
                "rediss://:secret@redis:6380/0?ssl_cert_reqs=required",
                "rediss://:secret@redis:6380/1?ssl_cert_reqs=required",
                id="tls_with_query",
            ),
        ],
    )
    def test_cache_url_from_broker_replaces_only_db_number(self, broker_url, expected):
        """パスの DB 番号だけを 1 に替え、認証情報・ホスト・クエリは残す."""
        assert cache_url_from_broker(broker_url) == expected

    @pytest.mark.parametrize(
        "broker_url",
        [
            pytest.param("amqp://guest@rabbitmq:5672//", id="not_redis"),
            pytest.param("unix:///run/redis/redis.sock", id="unix_socket"),
            pytest.param("redis://redis:6379?db=0", id="db_in_query"),
            pytest.param("redis://redis:6379/cache", id="non_numeric_path"),
            pytest.param("", id="empty"),
        ],
    )
    def test_cache_url_from_broker_without_db_in_path_raises(self, broker_url):
        """DB 番号をパスで表さない URL は替えられないので、設定を求める."""
        with pytest.raises(ValueError, match="CACHE_REDIS_URL"):
            cache_url_from_broker(broker_url)

    def test_cache_url_from_broker_error_does_not_include_url(self):
        """URL は秘密を含み得るので、エラーの文言に出さない."""
        with pytest.raises(ValueError) as excinfo:
            cache_url_from_broker("amqp://user:secret@rabbitmq:5672//")

        assert "secret" not in str(excinfo.value)


@pytest.mark.unit
class TestCacheSettings:
    """settings.py の CACHES."""

    def test_caches_without_cache_url_uses_db_1_of_broker(self, monkeypatch):
        """CACHE_REDIS_URL がなければ、Celery の接続先の DB 1 を全ワーカーで使う."""
        values = _load_settings(
            monkeypatch,
            CACHE_REDIS_URL=None,
            CELERY_BROKER_URL="redis://broker:6379/0",
        )

        default = values["CACHES"]["default"]
        assert default["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
        assert default["LOCATION"] == "redis://broker:6379/1"
        assert default["KEY_PREFIX"] == "kawashiro"

    def test_caches_without_any_url_uses_compose_redis_db_1(self, monkeypatch):
        """どちらも未設定なら、Compose の redis コンテナの DB 1 を使う."""
        values = _load_settings(
            monkeypatch, CACHE_REDIS_URL=None, CELERY_BROKER_URL=None
        )

        assert values["CACHES"]["default"]["LOCATION"] == "redis://redis:6379/1"

    def test_caches_with_empty_cache_url_falls_back_to_broker(self, monkeypatch):
        """`.env.sample` のように空で書いた CACHE_REDIS_URL は未設定と同じ."""
        values = _load_settings(
            monkeypatch,
            CACHE_REDIS_URL="",
            CELERY_BROKER_URL="redis://broker:6379/0",
        )

        assert values["CACHES"]["default"]["LOCATION"] == "redis://broker:6379/1"

    def test_caches_with_cache_url_uses_it_as_is(self, monkeypatch):
        """CACHE_REDIS_URL があればそのまま使う（ブローカーの URL は見ない）."""
        values = _load_settings(
            monkeypatch,
            CACHE_REDIS_URL="redis://cache:6379/3",
            CELERY_BROKER_URL="amqp://guest@rabbitmq:5672//",
        )

        assert values["CACHES"]["default"]["LOCATION"] == "redis://cache:6379/3"

    def test_caches_bound_redis_waits(self, monkeypatch):
        """Redis が応答しないときに、ワーカーを待たせ続けない."""
        values = _load_settings(monkeypatch, CACHE_REDIS_URL="redis://cache:6379/3")

        options = values["CACHES"]["default"]["OPTIONS"]
        assert 0 < options["socket_connect_timeout"] <= 5
        assert 0 < options["socket_timeout"] <= 5

    def test_tests_use_in_process_cache(self):
        """テストではプロセス内のキャッシュを使う（CI に Redis はない）."""
        assert isinstance(caches["default"], LocMemCache)
