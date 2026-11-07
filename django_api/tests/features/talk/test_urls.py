"""Talk の URL のテスト（チャットの API だけを公開し、旧会話生成の API はない）."""

import pytest
from django.urls import NoReverseMatch, Resolver404, resolve, reverse

# 旧会話生成（Talk Generator）の API。外部の自動化は Companion（/companion/run/）へ移した
REMOVED_PATHS = ("/talk/synthesize/", "/talk/configs/", "/talk/datetime/")
REMOVED_URL_NAMES = ("talk:synthesize", "talk:configs", "talk:datetime")


@pytest.mark.api
@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/talk/synthesize/"),
        ("get", "/talk/configs/"),
        ("get", "/talk/datetime/"),
    ],
)
def test_removed_generator_endpoint_returns_404(authenticated_client, method, path):
    """旧会話生成の API（単発の生成・プリセット一覧・日時情報）は 404."""
    response = authenticated_client.generic(method.upper(), path)

    assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.parametrize("path", REMOVED_PATHS)
def test_removed_generator_path_is_not_routed(path):
    """旧会話生成のパスはどのビューにも振り分けない."""
    with pytest.raises(Resolver404):
        resolve(path)


@pytest.mark.unit
@pytest.mark.parametrize("name", REMOVED_URL_NAMES)
def test_removed_generator_url_name_cannot_be_reversed(name):
    """旧会話生成の URL 名は引けない."""
    with pytest.raises(NoReverseMatch):
        reverse(name)
