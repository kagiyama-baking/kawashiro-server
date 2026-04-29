"""pytest設定とフィクスチャ定義"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """APIクライアントのフィクスチャ"""
    return APIClient()


@pytest.fixture
def regular_user(db):
    """一般ユーザーのフィクスチャ"""
    user = User.objects.create_user(
        email="test@example.com", password="testpass123", name="Test User"
    )
    return user


@pytest.fixture
def superuser(db):
    """スーパーユーザーのフィクスチャ"""
    user = User.objects.create_superuser(
        email="admin@example.com", password="adminpass123"
    )
    user.name = "Admin User"
    user.save()
    return user


@pytest.fixture
def auth_token(regular_user):
    """認証トークンのフィクスチャ"""
    token, _ = Token.objects.get_or_create(user=regular_user)
    return token


@pytest.fixture
def superuser_token(superuser):
    """スーパーユーザー用認証トークンのフィクスチャ"""
    token, _ = Token.objects.get_or_create(user=superuser)
    return token


@pytest.fixture
def authenticated_client(api_client, auth_token):
    """認証済みAPIクライアントのフィクスチャ"""
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {auth_token.key}")
    return api_client


@pytest.fixture
def superuser_client(api_client, superuser_token):
    """スーパーユーザー認証済みAPIクライアントのフィクスチャ"""
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {superuser_token.key}")
    return api_client


@pytest.fixture
def mock_file():
    """テスト用ファイルオブジェクトのフィクスチャ"""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name="test_file.txt", content=b"Test file content", content_type="text/plain"
    )


@pytest.fixture
def mock_pdf_file():
    """テスト用PDFファイルオブジェクトのフィクスチャ"""
    from django.core.files.uploadedfile import SimpleUploadedFile

    # 簡単なPDFヘッダー（実際のPDFではないが、テストには十分）
    pdf_content = b"%PDF-1.4\n%Test PDF content"
    return SimpleUploadedFile(
        name="test_document.pdf", content=pdf_content, content_type="application/pdf"
    )


@pytest.fixture
def mock_ms_graph_settings():
    """MSGraphSettings用のモックフィクスチャ"""
    from unittest.mock import patch

    from integrations.msgraph.config import MSGraphSettings

    settings = MSGraphSettings(
        tenant_id="test-tenant",
        client_id="test-client",
        cert_thumbprint="test-thumb",
        private_key="-----BEGIN PRIVATE KEY-----\nKEY_DATA\n-----END PRIVATE KEY-----",
        target_user="test@example.com",
    )

    with patch(
        "integrations.msgraph.base.get_ms_graph_settings", return_value=settings
    ):
        yield settings


@pytest.fixture
def ms_graph_client(mock_ms_graph_settings):
    """モック設定を使用したOneDriveMSGraphClientのフィクスチャ"""
    from integrations.msgraph import OneDriveMSGraphClient

    client = OneDriveMSGraphClient()
    client._access_token = "test-token"
    return client
