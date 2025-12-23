"""Tests for assistant serializers."""

from assistant.serializers import (
    ChatRequestSerializer,
    ChatResponseSerializer,
    DailySummaryRequestSerializer,
    DailySummaryResponseSerializer,
    GreetingRequestSerializer,
    GreetingResponseSerializer,
)


class TestGreetingRequestSerializer:
    """GreetingRequestSerializerのテスト."""

    def test_valid_data(self):
        """有効なデータでバリデーション成功."""
        data = {
            "area_code": "130010",
            "greeting_type": "morning",
            "include_audio": True,
        }
        serializer = GreetingRequestSerializer(data=data)
        assert serializer.is_valid()

    def test_valid_data_with_defaults(self):
        """デフォルト値が適用される."""
        data = {}
        serializer = GreetingRequestSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data["greeting_type"] == "morning"
        assert serializer.validated_data["include_audio"] is False

    def test_area_code_optional(self):
        """area_codeはオプション."""
        data = {"greeting_type": "morning"}
        serializer = GreetingRequestSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data.get("area_code") is None

    def test_invalid_greeting_type(self):
        """無効なgreeting_typeでエラー."""
        data = {"area_code": "130010", "greeting_type": "invalid"}
        serializer = GreetingRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "greeting_type" in serializer.errors

    def test_valid_greeting_types(self):
        """有効なgreeting_typeが受け入れられる."""
        for greeting_type in ["morning", "afternoon", "evening"]:
            data = {"area_code": "130010", "greeting_type": greeting_type}
            serializer = GreetingRequestSerializer(data=data)
            assert serializer.is_valid(), f"Failed for {greeting_type}"


class TestGreetingResponseSerializer:
    """GreetingResponseSerializerのテスト."""

    def test_response_serialization(self):
        """レスポンスのシリアライズ."""
        data = {
            "text": "おはようございます。",
            "events_count": 2,
            "weather_summary": "晴れ 最高気温15℃",
            "thinking": "予定と天気を確認しました。",
            "tools_used": ["get_today_events", "get_weather_forecast"],
            "audio": "data:audio/wav;base64,UklGRg==",
        }
        serializer = GreetingResponseSerializer(data)
        assert serializer.data["text"] == "おはようございます。"
        assert serializer.data["events_count"] == 2
        assert serializer.data["thinking"] == "予定と天気を確認しました。"
        assert "get_today_events" in serializer.data["tools_used"]

    def test_response_without_audio(self):
        """音声なしのレスポンス."""
        data = {
            "text": "おはようございます。",
            "events_count": 0,
            "weather_summary": "晴れ",
            "thinking": None,
            "tools_used": [],
            "audio": None,
        }
        serializer = GreetingResponseSerializer(data)
        assert serializer.data["audio"] is None
        assert serializer.data["thinking"] is None
        assert serializer.data["tools_used"] == []

    def test_response_without_weather(self):
        """天気情報なしのレスポンス."""
        data = {
            "text": "おはようございます。",
            "events_count": 1,
            "weather_summary": None,
            "thinking": "予定を確認しました。",
            "tools_used": ["get_today_events"],
            "audio": None,
        }
        serializer = GreetingResponseSerializer(data)
        assert serializer.data["weather_summary"] is None


class TestChatRequestSerializer:
    """ChatRequestSerializerのテスト."""

    def test_valid_data(self):
        """有効なデータでバリデーション成功."""
        data = {
            "message": "今日の予定を教えて",
            "area_code": "130010",
            "include_audio": False,
        }
        serializer = ChatRequestSerializer(data=data)
        assert serializer.is_valid()

    def test_message_required(self):
        """messageが必須."""
        data = {"area_code": "130010"}
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "message" in serializer.errors

    def test_area_code_optional(self):
        """area_codeはオプション."""
        data = {"message": "こんにちは"}
        serializer = ChatRequestSerializer(data=data)
        assert serializer.is_valid()

    def test_message_max_length(self):
        """messageの最大長チェック."""
        data = {"message": "a" * 1001}  # 1000文字制限と仮定
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "message" in serializer.errors


class TestChatResponseSerializer:
    """ChatResponseSerializerのテスト."""

    def test_response_serialization(self):
        """レスポンスのシリアライズ."""
        data = {
            "reply": "今日の予定は2件です。",
            "tools_used": ["get_today_events"],
            "audio": None,
        }
        serializer = ChatResponseSerializer(data)
        assert serializer.data["reply"] == "今日の予定は2件です。"
        assert "get_today_events" in serializer.data["tools_used"]


class TestDailySummaryRequestSerializer:
    """DailySummaryRequestSerializerのテスト."""

    def test_valid_data(self):
        """有効なデータでバリデーション成功."""
        data = {"area_code": "130010", "include_audio": True}
        serializer = DailySummaryRequestSerializer(data=data)
        assert serializer.is_valid()

    def test_area_code_required(self):
        """area_codeが必須."""
        data = {"include_audio": False}
        serializer = DailySummaryRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "area_code" in serializer.errors


class TestDailySummaryResponseSerializer:
    """DailySummaryResponseSerializerのテスト."""

    def test_response_serialization(self):
        """レスポンスのシリアライズ."""
        data = {
            "summary": "本日の予定は2件です。",
            "date": "2024-12-24",
            "audio": None,
        }
        serializer = DailySummaryResponseSerializer(data)
        assert serializer.data["summary"] == "本日の予定は2件です。"
        assert serializer.data["date"] == "2024-12-24"
