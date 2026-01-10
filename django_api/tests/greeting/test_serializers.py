"""Tests for greeting serializers."""

from greeting.serializers import MorningGreetingResponseSerializer


class TestMorningGreetingResponseSerializer:
    """MorningGreetingResponseSerializerのテスト"""

    def test_valid_response(self):
        """有効なレスポンスデータでシリアライズできる"""
        data = {
            "greeting_text": "おはようございます、先輩。",
        }
        serializer = MorningGreetingResponseSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_missing_greeting_text(self):
        """greeting_text がない場合はエラー"""
        data = {}
        serializer = MorningGreetingResponseSerializer(data=data)
        assert not serializer.is_valid()
        assert "greeting_text" in serializer.errors
