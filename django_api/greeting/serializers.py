"""Serializers for greeting app."""

from rest_framework import serializers


class MorningGreetingResponseSerializer(serializers.Serializer):
    """朝の挨拶レスポンスのシリアライザー."""

    greeting_text = serializers.CharField(
        help_text="生成された挨拶テキスト",
    )
