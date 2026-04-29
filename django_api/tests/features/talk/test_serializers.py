"""Tests for talk serializers."""

import pytest

from features.talk.serializers import (
    TalkRequestSerializer,
    TalkResponseSerializer,
    TodayInfoResponseSerializer,
)


class TestTalkRequestSerializer:
    """TalkRequestSerializerのテスト"""

    def test_valid_request_with_config_name(self):
        """config_name のみで有効。ユーザープロンプトなしでも valid."""
        data = {"config_name": "morning"}
        serializer = TalkRequestSerializer(data=data)

        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["config_name"] == "morning"
        assert "user_prompt" not in serializer.validated_data

    @pytest.mark.parametrize(
        "config_name",
        [
            pytest.param(None, id="missing"),
            pytest.param("", id="empty"),
        ],
    )
    def test_invalid_config_name(self, config_name):
        """config_name が不正な場合はエラー."""
        data = {} if config_name is None else {"config_name": config_name}
        serializer = TalkRequestSerializer(data=data)

        assert not serializer.is_valid()
        assert "config_name" in serializer.errors

    @pytest.mark.parametrize(
        "user_prompt, expected_valid",
        [
            pytest.param("カスタムプロンプト", True, id="short_text"),
            pytest.param("あ" * 4000, True, id="exactly_max_length"),
            pytest.param("あ" * 4001, False, id="over_max_length"),
        ],
    )
    def test_user_prompt_validation(self, user_prompt, expected_valid):
        """user_prompt の境界値バリデーション."""
        data = {"config_name": "morning", "user_prompt": user_prompt}
        serializer = TalkRequestSerializer(data=data)

        if expected_valid:
            assert serializer.is_valid(), serializer.errors
            assert serializer.validated_data["user_prompt"] == user_prompt
        else:
            assert not serializer.is_valid()
            assert "user_prompt" in serializer.errors


class TestTalkResponseSerializer:
    """TalkResponseSerializerのテスト"""

    @pytest.mark.parametrize(
        "data, expected_valid",
        [
            pytest.param(
                {"greeting_text": "おはようございます、先輩。"}, True, id="valid"
            ),
            pytest.param({}, False, id="missing_greeting_text"),
        ],
    )
    def test_response_validation(self, data, expected_valid):
        """レスポンスのバリデーション."""
        serializer = TalkResponseSerializer(data=data)

        if expected_valid:
            assert serializer.is_valid(), serializer.errors
        else:
            assert not serializer.is_valid()
            assert "greeting_text" in serializer.errors


class TestTodayInfoResponseSerializer:
    """TodayInfoResponseSerializerのテスト"""

    def test_valid_response(self):
        """有効なレスポンスデータでシリアライズできる（祝日なし）."""
        data = {
            "date": "2025-01-14",
            "time": "09:30:00",
            "day_of_week": "Tuesday",
            "day_of_week_ja": "火曜日",
            "holiday_name": None,
        }
        serializer = TodayInfoResponseSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
