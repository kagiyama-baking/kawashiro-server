"""ヘルスチェックエンドポイントのテスト"""

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from rest_framework import status

from health.middleware import HealthCheckMiddleware


@pytest.mark.unit
class TestHealthCheckMiddleware:
    """HealthCheckMiddleware のテスト"""

    def test_health_check_returns_200(self, api_client):
        """GET /health/ で200が返ること"""
        response = api_client.get("/health/")

        assert response.status_code == status.HTTP_200_OK

    def test_health_check_returns_status_ok(self, api_client):
        """レスポンスボディに{"status": "ok"}が含まれること"""
        response = api_client.get("/health/")

        assert response.json() == {"status": "ok"}

    def test_health_check_requires_no_authentication(self, api_client):
        """認証ヘッダーなしでもアクセスできること"""
        response = api_client.get("/health/")

        assert response.status_code == status.HTTP_200_OK

    def test_health_check_bypasses_allowed_hosts(self):
        """ALLOWED_HOSTSに含まれないHostヘッダーでも200が返ること"""
        factory = RequestFactory()
        request = factory.get("/health/", HTTP_HOST="unknown-host.example.com")

        def dummy_get_response(req):
            raise AssertionError("ヘルスチェックはミドルウェアチェーンを通過すべきでない")

        middleware = HealthCheckMiddleware(dummy_get_response)
        response = middleware(request)

        assert response.status_code == status.HTTP_200_OK

    @override_settings(ALLOWED_HOSTS=["allowed.example.com"])
    def test_non_health_path_passes_through(self):
        """ヘルスチェック以外のパスはミドルウェアチェーンに渡されること"""
        factory = RequestFactory()
        request = factory.get("/other/")

        passed_through = False

        def mock_get_response(req):
            nonlocal passed_through
            passed_through = True
            return HttpResponse("ok")

        middleware = HealthCheckMiddleware(mock_get_response)
        middleware(request)

        assert passed_through is True
