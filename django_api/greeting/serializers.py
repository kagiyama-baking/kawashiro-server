"""Serializers for greeting app."""

from rest_framework import serializers


class GreetingResponseSerializer(serializers.Serializer):
    """挨拶レスポンスのシリアライザー."""

    greeting_text = serializers.CharField(
        help_text="生成された挨拶テキスト",
    )


# 後方互換性のためのエイリアス
MorningGreetingResponseSerializer = GreetingResponseSerializer
EveningGreetingResponseSerializer = GreetingResponseSerializer
WelcomeHomeGreetingResponseSerializer = GreetingResponseSerializer


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
