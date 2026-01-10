"""E2E tests for Yahoo transit client.

これらのテストは実際のYahoo!乗換案内にアクセスします。
CIで定期実行し、スクレイピング対象の構造変更を検知するために使用します。

実行方法:
    pytest tests/train/test_yahoo_client_e2e.py -v -m e2e

注意:
    - ネットワーク接続が必要
    - Yahoo!側の負荷を考慮し、頻繁に実行しないこと
    - CI では schedule (例: 毎日1回) での実行を推奨
"""

import pytest

from train.yahoo_client import YahooTransitClient


@pytest.mark.e2e
class TestYahooTransitClientE2E:
    """Yahoo!乗換案内への実際のアクセスを伴うE2Eテスト"""

    def test_fetch_diainfo_structure_check(self):
        """実際のレスポンスから必要なフィールドが取得できることを確認

        このテストが失敗した場合、Yahoo!側のJSON構造が変更された可能性があります。
        yahoo_client.py の _extract_diainfo メソッドの修正が必要です。
        """
        client = YahooTransitClient(timeout=30)

        # 山手線(58)を使用
        result = client.fetch_diainfo("58")

        # 必須フィールドの存在確認
        assert "rail_id" in result, "rail_id フィールドがありません"
        assert "rail_name" in result, "rail_name フィールドがありません"
        assert "company_name" in result, "company_name フィールドがありません"
        assert "status" in result, "status フィールドがありません"
        assert "is_delayed" in result, "is_delayed フィールドがありません"
        assert "message" in result, "message フィールドがありません"
        assert "update_time" in result, "update_time フィールドがありません"
        assert "error" in result, "error フィールドがありません"

        # 値の妥当性確認
        assert result["rail_id"] == "58"
        assert result["rail_name"] is not None, (
            "rail_name が None です（構造変更の可能性）"
        )
        assert result["company_name"] is not None, "company_name が None です"
        assert result["status"] is not None, "status が None です"
        assert isinstance(result["is_delayed"], bool), (
            "is_delayed が bool ではありません"
        )
        assert result["error"] is None, f"エラーが発生: {result['error']}"

    def test_fetch_diainfo_json_structure_exists(self):
        """__NEXT_DATA__ JSONが存在し、期待する構造を持つことを確認"""
        import json
        import re

        import requests

        url = "https://transit.yahoo.co.jp/diainfo/58/0"
        response = requests.get(
            url,
            timeout=30,
        )

        # __NEXT_DATA__ の存在確認
        pattern = r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'
        match = re.search(pattern, response.text, re.DOTALL)
        assert match, "__NEXT_DATA__ スクリプトタグが見つかりません（構造変更の可能性）"

        # JSONパース確認
        data = json.loads(match.group(1))

        # 必要なキーパスの存在確認
        assert "props" in data, "props キーがありません"
        assert "pageProps" in data["props"], "pageProps キーがありません"

        page_props = data["props"]["pageProps"]
        assert "diainfoTrainFeature" in page_props, (
            "diainfoTrainFeature キーがありません"
        )

        feature = page_props["diainfoTrainFeature"]
        assert "routeInfo" in feature, "routeInfo キーがありません"

        route_info = feature["routeInfo"]
        # property内またはrouteInfo直下にデータがある
        route_props = route_info.get("property", route_info)

        assert "displayName" in route_props, "displayName キーがありません（構造変更）"
        assert "companyName" in route_props, "companyName キーがありません（構造変更）"

    def test_multiple_rails_fetch(self):
        """複数路線の取得が正常に動作することを確認"""
        client = YahooTransitClient(timeout=30)

        # 複数の主要路線をテスト
        rail_ids = ["58", "50", "131"]  # 山手線、埼京線、都営大江戸線
        results = client.fetch_multiple_diainfo(rail_ids)

        assert len(results) == 3

        for i, result in enumerate(results):
            assert result["rail_id"] == rail_ids[i]
            # エラーがないか、または路線名が取得できていることを確認
            if result["error"] is None:
                assert result["rail_name"] is not None
                assert result["status"] is not None
