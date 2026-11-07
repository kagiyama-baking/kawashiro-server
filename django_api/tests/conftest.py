"""pytest設定とフィクスチャ定義"""

import os
from unittest.mock import patch

import pydantic_ai.models
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from pydantic_ai.models import override_allow_model_requests
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from tests.fixtures.langfuse import FakeLangfuse
from tests.fixtures.llm import FakeLiteLLM

# 開発者の .env に Langfuse キーがあってもテストからトレースを送らない。
# Langfuse クライアントは生成時にこの値を読むので、テスト実行より前に設定する。
os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

# テストから実 LLM へリクエストを送らない（TestModel / FunctionModel は対象外）。
pydantic_ai.models.ALLOW_MODEL_REQUESTS = False

User = get_user_model()


@pytest.fixture(autouse=True)
def _in_process_cache(settings):
    """キャッシュを Redis からプロセス内のものに替え、テストの前後で空にする.

    CI の django-api-test に Redis はない。LocMemCache は LOCATION が同じなら
    インスタンスをまたいで中身を共有するので、空にしないとスロットルの計数が
    次のテストへ持ち越される。
    """
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "kawashiro-tests",
        }
    }
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fake_litellm(mocker):
    """`open_model` が作る AsyncOpenAI の HTTP 層だけを差し替える（ネットワークへ出ない）."""

    def install(*script) -> FakeLiteLLM:
        fake = FakeLiteLLM(*script)
        mocker.patch(
            "integrations.llm.runtime.AsyncOpenAI", side_effect=fake.build_client
        )
        return fake

    with override_allow_model_requests(True):
        yield install


@pytest.fixture
def langfuse_prompts():
    """Langfuse の text プロンプトの代役（`(プロンプト名, ラベル) → 本文` の dict）.

    使ったテストは Langfuse へ出ない。本文を返させたいテストは dict に入れる。
    入れていない名前・ラベルは SDK と同じく NotFoundError で取得に失敗する。
    companion のテストでは autouse（tests/features/companion/conftest.py）。
    """
    prompts: dict[tuple[str, str], str] = {}
    with patch("langfuse.get_client", return_value=FakeLangfuse(prompts)):
        yield prompts


@pytest.fixture
def langfuse_unreachable(langfuse_prompts):
    """Langfuse に届かない（クライアントを用意できない。入れた本文も返らない）."""
    with patch(
        "langfuse.get_client", side_effect=ConnectionError("Langfuse に届きません")
    ):
        yield


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
def _static_storage_without_manifest(settings):
    """管理画面のテンプレートを描画できるよう、manifest を使わない保存先にする.

    テストの前に collectstatic はしないので、本番と同じ manifest 付きの保存先では
    テンプレートの `{% static %}` が manifest にない名前で失敗する。
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


@pytest.fixture
def admin_site_client(client, superuser, _static_storage_without_manifest):
    """管理画面にスーパーユーザーでログインしたクライアント（画面を描画できる）."""
    client.force_login(superuser)
    return client


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
