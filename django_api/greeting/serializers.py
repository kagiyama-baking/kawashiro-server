"""Serializers for greeting app."""

from rest_framework import serializers


class GreetingRequestSerializer(serializers.Serializer):
    """挨拶リクエストのシリアライザー."""

    config_name = serializers.CharField(
        required=True,
        max_length=50,
        help_text="設定名（管理画面で登録した name）",
    )
    user_prompt = serializers.CharField(
        required=True,
        max_length=10000,
        help_text="ユーザープロンプトテンプレート",
    )


class GreetingResponseSerializer(serializers.Serializer):
    """挨拶レスポンスのシリアライザー."""

    greeting_text = serializers.CharField(
        help_text="生成された挨拶テキスト",
    )


class TodayInfoResponseSerializer(serializers.Serializer):
    """本日の日時情報レスポンスのシリアライザー."""

    date = serializers.CharField(
        help_text="日付（YYYY-MM-DD形式）",
    )
    time = serializers.CharField(
        help_text="時刻（HH:MM:SS形式）",
    )
    day_of_week = serializers.CharField(
        help_text="曜日（英語）",
    )
    day_of_week_ja = serializers.CharField(
        help_text="曜日（日本語）",
    )
    holiday_name = serializers.CharField(
        allow_null=True,
        help_text="祝日名（祝日でない場合はnull）",
    )
