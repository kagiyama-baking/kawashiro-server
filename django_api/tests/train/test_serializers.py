"""Tests for train serializers."""

from train.serializers import DiainfoRequestSerializer, DiainfoResponseSerializer


class TestDiainfoRequestSerializer:
    """Tests for DiainfoRequestSerializer."""

    def test_valid_single_rail_id(self):
        """単一の路線IDが有効"""
        serializer = DiainfoRequestSerializer(data={"rail_ids": "131"})
        assert serializer.is_valid()
        assert serializer.validated_data["rail_ids"] == ["131"]

    def test_valid_multiple_rail_ids_comma_separated(self):
        """カンマ区切りの複数路線IDが有効"""
        serializer = DiainfoRequestSerializer(data={"rail_ids": "131,22,35"})
        assert serializer.is_valid()
        assert serializer.validated_data["rail_ids"] == ["131", "22", "35"]

    def test_valid_multiple_rail_ids_with_spaces(self):
        """スペースを含むカンマ区切りも有効"""
        serializer = DiainfoRequestSerializer(data={"rail_ids": "131, 22, 35"})
        assert serializer.is_valid()
        assert serializer.validated_data["rail_ids"] == ["131", "22", "35"]

    def test_invalid_missing_rail_ids(self):
        """rail_idsが指定されていない場合は無効"""
        serializer = DiainfoRequestSerializer(data={})
        assert not serializer.is_valid()
        assert "rail_ids" in serializer.errors

    def test_invalid_empty_rail_ids(self):
        """rail_idsが空文字の場合は無効"""
        serializer = DiainfoRequestSerializer(data={"rail_ids": ""})
        assert not serializer.is_valid()
        assert "rail_ids" in serializer.errors

    def test_invalid_too_many_rail_ids(self):
        """路線IDが10個を超える場合は無効"""
        rail_ids = ",".join([str(i) for i in range(11)])
        serializer = DiainfoRequestSerializer(data={"rail_ids": rail_ids})
        assert not serializer.is_valid()
        assert "rail_ids" in serializer.errors

    def test_invalid_non_numeric_rail_id(self):
        """数値以外の路線IDは無効（セキュリティ対策）"""
        serializer = DiainfoRequestSerializer(data={"rail_ids": "abc"})
        assert not serializer.is_valid()
        assert "rail_ids" in serializer.errors

    def test_invalid_path_traversal_attempt(self):
        """パストラバーサル攻撃は無効"""
        serializer = DiainfoRequestSerializer(data={"rail_ids": "../etc/passwd"})
        assert not serializer.is_valid()
        assert "rail_ids" in serializer.errors

    def test_invalid_mixed_numeric_and_non_numeric(self):
        """数値と非数値が混在する場合は無効"""
        serializer = DiainfoRequestSerializer(data={"rail_ids": "131,abc,22"})
        assert not serializer.is_valid()
        assert "rail_ids" in serializer.errors


class TestDiainfoResponseSerializer:
    """Tests for DiainfoResponseSerializer."""

    def test_serialize_normal_operation(self):
        """平常運転の運行情報をシリアライズできる"""
        data = {
            "rail_id": "131",
            "rail_name": "都営大江戸線",
            "company_name": "東京都交通局",
            "status": "平常運転",
            "is_delayed": False,
            "message": "現在､事故･遅延に関する情報はありません。",
            "cause": None,
            "update_time": "2026-01-08 09:00:00",
            "error": None,
        }
        serializer = DiainfoResponseSerializer(data)
        result = serializer.data

        assert result["rail_id"] == "131"
        assert result["rail_name"] == "都営大江戸線"
        assert result["is_delayed"] is False
        assert result["cause"] is None

    def test_serialize_delayed_operation(self):
        """遅延時の運行情報をシリアライズできる"""
        data = {
            "rail_id": "22",
            "rail_name": "京浜東北根岸線",
            "company_name": "JR東日本",
            "status": "列車遅延",
            "is_delayed": True,
            "message": "混雑の影響で、一部列車に遅れが出ています。",
            "cause": "混雑",
            "update_time": "2026-01-08 08:55:00",
            "error": None,
        }
        serializer = DiainfoResponseSerializer(data)
        result = serializer.data

        assert result["is_delayed"] is True
        assert result["cause"] == "混雑"

    def test_serialize_multiple(self):
        """複数の運行情報をシリアライズできる"""
        data = [
            {
                "rail_id": "131",
                "rail_name": "都営大江戸線",
                "company_name": "東京都交通局",
                "status": "平常運転",
                "is_delayed": False,
                "message": "現在､事故･遅延に関する情報はありません。",
                "cause": None,
                "update_time": "2026-01-08 09:00:00",
                "error": None,
            },
            {
                "rail_id": "22",
                "rail_name": "京浜東北根岸線",
                "company_name": "JR東日本",
                "status": "列車遅延",
                "is_delayed": True,
                "message": "混雑の影響で、一部列車に遅れが出ています。",
                "cause": "混雑",
                "update_time": "2026-01-08 08:55:00",
                "error": None,
            },
        ]
        serializer = DiainfoResponseSerializer(data, many=True)
        result = serializer.data

        assert len(result) == 2
        assert result[0]["rail_name"] == "都営大江戸線"
        assert result[1]["rail_name"] == "京浜東北根岸線"

    def test_serialize_with_error(self):
        """エラー発生時の情報をシリアライズできる"""
        data = {
            "rail_id": "99999",
            "rail_name": None,
            "company_name": None,
            "status": None,
            "is_delayed": None,
            "message": None,
            "cause": None,
            "update_time": None,
            "error": "路線IDが見つかりません",
        }
        serializer = DiainfoResponseSerializer(data)
        result = serializer.data

        assert result["rail_id"] == "99999"
        assert result["error"] == "路線IDが見つかりません"
