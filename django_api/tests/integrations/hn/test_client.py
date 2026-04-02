"""HN Algolia APIクライアントのテスト."""

from unittest.mock import Mock, patch

import pytest
import requests

from integrations.hn.client import HNAlgoliaClient, HNComment, HNStory
from integrations.hn.exceptions import HNNetworkError, HNParseError, HNTimeoutError


@pytest.mark.unit
class TestHNAlgoliaClient:
    """HNAlgoliaClientのテスト."""

    @pytest.fixture
    def client(self):
        """テスト用クライアント."""
        return HNAlgoliaClient(timeout=5)

    @pytest.fixture
    def sample_search_response(self):
        """Algolia検索APIのサンプルレスポンス."""
        return {
            "hits": [
                {
                    "objectID": "12345",
                    "title": "Show HN: A new programming language",
                    "url": "https://example.com/lang",
                    "author": "testuser",
                    "points": 250,
                    "num_comments": 150,
                    "created_at": "2026-04-01T12:00:00.000Z",
                },
                {
                    "objectID": "12346",
                    "title": "Ask HN: Best practices for TDD?",
                    "url": None,
                    "author": "anotheruser",
                    "points": 80,
                    "num_comments": 45,
                    "created_at": "2026-04-01T10:00:00.000Z",
                },
            ],
            "nbHits": 2,
            "page": 0,
            "nbPages": 1,
        }

    @pytest.fixture
    def sample_item_response(self):
        """アイテムAPIのサンプルレスポンス."""
        return {
            "id": 12345,
            "title": "Show HN: A new programming language",
            "url": "https://example.com/lang",
            "author": "testuser",
            "points": 250,
            "children": [
                {
                    "id": 12347,
                    "author": "commenter1",
                    "text": "This looks great!",
                    "parent_id": 12345,
                    "children": [
                        {
                            "id": 12348,
                            "author": "commenter2",
                            "text": "I agree, very impressive.",
                            "parent_id": 12347,
                            "children": [],
                        }
                    ],
                },
                {
                    "id": 12349,
                    "author": "commenter3",
                    "text": "How does it compare to Rust?",
                    "parent_id": 12345,
                    "children": [],
                },
            ],
        }

    @patch("integrations.hn.client.requests.get")
    def test_get_front_page_stories_returns_stories(
        self, mock_get, client, sample_search_response
    ):
        """フロントページからストーリーを正常取得できる."""
        mock_response = Mock()
        mock_response.json.return_value = sample_search_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        stories = client.get_front_page_stories()

        assert len(stories) == 2
        assert isinstance(stories[0], HNStory)
        assert stories[0].hn_id == 12345
        assert stories[0].title == "Show HN: A new programming language"
        assert stories[0].url == "https://example.com/lang"
        assert stories[0].score == 250
        assert stories[0].num_comments == 150

    @patch("integrations.hn.client.requests.get")
    def test_get_front_page_stories_handles_null_url(
        self, mock_get, client, sample_search_response
    ):
        """URLがnullのストーリー（Ask HN等）を正しく処理できる."""
        mock_response = Mock()
        mock_response.json.return_value = sample_search_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        stories = client.get_front_page_stories()

        assert stories[1].url == ""
        assert stories[1].title == "Ask HN: Best practices for TDD?"

    @patch("integrations.hn.client.requests.get")
    def test_get_front_page_stories_sends_correct_params(
        self, mock_get, client, sample_search_response
    ):
        """正しいクエリパラメータでAPIを呼び出す."""
        mock_response = Mock()
        mock_response.json.return_value = sample_search_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client.get_front_page_stories(hits_per_page=50)

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs["params"]["hitsPerPage"] == 50
        assert call_kwargs.kwargs["params"]["tags"] == "front_page"

    @patch("integrations.hn.client.requests.get")
    def test_get_front_page_stories_empty_response(self, mock_get, client):
        """空のレスポンスを正しく処理できる."""
        mock_response = Mock()
        mock_response.json.return_value = {"hits": [], "nbHits": 0}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        stories = client.get_front_page_stories()

        assert stories == []

    @patch("integrations.hn.client.requests.get")
    def test_get_item_returns_item_data(self, mock_get, client, sample_item_response):
        """アイテムデータを正常取得できる."""
        mock_response = Mock()
        mock_response.json.return_value = sample_item_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        item = client.get_item(12345)

        assert item["id"] == 12345
        assert item["title"] == "Show HN: A new programming language"

    @patch("integrations.hn.client.requests.get")
    def test_get_comments_returns_tree_structure(
        self, mock_get, client, sample_item_response
    ):
        """コメントをツリー構造で取得できる."""
        mock_response = Mock()
        mock_response.json.return_value = sample_item_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        comments = client.get_comments(12345)

        assert len(comments) == 2
        assert isinstance(comments[0], HNComment)
        assert comments[0].author == "commenter1"
        assert comments[0].text == "This looks great!"
        assert len(comments[0].children) == 1
        assert comments[0].children[0].author == "commenter2"

    @patch("integrations.hn.client.requests.get")
    def test_get_comments_respects_max_depth(
        self, mock_get, client, sample_item_response
    ):
        """最大深度を超えるコメントは取得しない."""
        mock_response = Mock()
        mock_response.json.return_value = sample_item_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        comments = client.get_comments(12345, max_depth=0)

        assert len(comments) == 2
        assert comments[0].children == []

    def test_flatten_comments(self, client):
        """ツリー構造をフラットに変換できる."""
        nested = HNComment(
            hn_id=2,
            author="b",
            text="reply",
            parent_id=1,
            children=[],
        )
        root = HNComment(
            hn_id=1,
            author="a",
            text="hello",
            parent_id=None,
            children=[nested],
        )

        flat = client.flatten_comments([root])

        assert len(flat) == 2
        assert flat[0].hn_id == 1
        assert flat[1].hn_id == 2

    @patch("integrations.hn.client.requests.get")
    def test_network_error_raises_hn_network_error(self, mock_get, client):
        """接続エラー時にHNNetworkErrorを送出する."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        with pytest.raises(HNNetworkError, match="接続に失敗しました"):
            client.get_front_page_stories()

    @patch("integrations.hn.client.requests.get")
    def test_timeout_raises_hn_timeout_error(self, mock_get, client):
        """タイムアウト時にHNTimeoutErrorを送出する."""
        mock_get.side_effect = requests.Timeout("Request timed out")

        with pytest.raises(HNTimeoutError, match="タイムアウト"):
            client.get_front_page_stories()

    @patch("integrations.hn.client.requests.get")
    def test_http_error_raises_hn_network_error(self, mock_get, client):
        """HTTPエラー時にHNNetworkErrorを送出する."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            response=mock_response
        )
        mock_get.return_value = mock_response

        with pytest.raises(HNNetworkError, match="エラーを返しました"):
            client.get_front_page_stories()

    @patch("integrations.hn.client.requests.get")
    def test_json_parse_error_raises_hn_parse_error(self, mock_get, client):
        """JSON解析エラー時にHNParseErrorを送出する."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        with pytest.raises(HNParseError, match="解析に失敗"):
            client.get_front_page_stories()
