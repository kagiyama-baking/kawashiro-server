"""Tests for talk serializers."""

from features.talk.serializers import (
    TalkRequestSerializer,
    TalkResponseSerializer,
    TodayInfoResponseSerializer,
)


class TestTalkRequestSerializer:
    """TalkRequestSerializerのテスト"""

    def test_valid_request_with_config_name(self):
        """config_name のみで有効."""
        data = {"config_name": "morning"}
        serializer = TalkRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["config_name"] == "morning"

    def test_missing_config_name(self):
        """config_name がない場合はエラー."""
        data = {}
        serializer = TalkRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "config_name" in serializer.errors

    def test_empty_config_name(self):
        """config_name が空の場合はエラー."""
        data = {"config_name": ""}
        serializer = TalkRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "config_name" in serializer.errors

    def test_accepts_optional_user_prompt(self):
        """user_prompt が指定された場合は受理される."""
        data = {"config_name": "morning", "user_prompt": "カスタムプロンプト"}
        serializer = TalkRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["user_prompt"] == "カスタムプロンプト"

    def test_user_prompt_is_optional(self):
        """user_prompt は任意で、省略可能."""
        data = {"config_name": "morning"}
        serializer = TalkRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert "user_prompt" not in serializer.validated_data

    def test_ignores_other_extra_fields(self):
        """未定義の追加フィールドは無視される."""
        data = {"config_name": "morning", "unknown_field": "ignored"}
        serializer = TalkRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert "unknown_field" not in serializer.validated_data

    def test_user_prompt_max_length_4000(self):
        """user_prompt は 4000 文字まで受理."""
        data = {"config_name": "morning", "user_prompt": "あ" * 4000}
        serializer = TalkRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_user_prompt_over_max_length_rejected(self):
        """user_prompt が 4000 文字を超えると 400."""
        data = {"config_name": "morning", "user_prompt": "あ" * 4001}
        serializer = TalkRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "user_prompt" in serializer.errors


class TestTalkResponseSerializer:
    """TalkResponseSerializerのテスト"""

    def test_valid_response(self):
        """有効なレスポンスデータでシリアライズできる."""
        data = {
            "greeting_text": "おはようございます、先輩。",
        }
        serializer = TalkResponseSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_missing_greeting_text(self):
        """greeting_text がない場合はエラー."""
        data = {}
        serializer = TalkResponseSerializer(data=data)
        assert not serializer.is_valid()
        assert "greeting_text" in serializer.errors


class TestTodayInfoResponseSerializer:
    """TodayInfoResponseSerializerのテスト"""

    def test_valid_response(self):
        """有効なレスポンスデータでシリアライズできる."""
        data = {
            "date": "2025-01-14",
            "time": "09:30:00",
            "day_of_week": "Tuesday",
            "day_of_week_ja": "火曜日",
            "holiday_name": None,
        }
        serializer = TodayInfoResponseSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_valid_response_with_holiday(self):
        """祝日がある場合も有効."""
        data = {
            "date": "2025-01-01",
            "time": "08:00:00",
            "day_of_week": "Wednesday",
            "day_of_week_ja": "水曜日",
            "holiday_name": "元日",
        }
        serializer = TodayInfoResponseSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
