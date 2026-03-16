"""ヘルスチェックエンドポイントのテスト"""

import pytest
from rest_framework import status


@pytest.mark.unit
class TestHealthCheckView:
    """GET /health/ のテスト"""

    def test_health_check_returns_200(self, api_client):
        """未認証でもGET /health/で200が返ること"""
        response = api_client.get("/health/")

        assert response.status_code == status.HTTP_200_OK

    def test_health_check_returns_status_ok(self, api_client):
        """レスポンスボディに{"status": "ok"}が含まれること"""
        response = api_client.get("/health/")

        assert response.data == {"status": "ok"}

    def test_health_check_requires_no_authentication(self, api_client):
        """認証ヘッダーなしでもアクセスできること"""
        response = api_client.get("/health/")

        assert response.status_code == status.HTTP_200_OK
