"""Serializers for weather app."""

from rest_framework import serializers


class WeatherRequestSerializer(serializers.Serializer):
    """天気予報リクエストのシリアライザー."""

    area_code = serializers.RegexField(
        regex=r"^\d{6}$",
        required=True,
        help_text="予報区コード（6桁の数字）。例: 130010=東京地方, 270000=大阪府",
    )
    day = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
        max_value=2,
        help_text="予報日（0: 今日, 1: 明日, 2: 明後日）。デフォルト: 0",
    )


class WeatherResponseSerializer(serializers.Serializer):
    """天気予報レスポンスのシリアライザー."""

    area_name = serializers.CharField(
        read_only=True,
        help_text="地域名（都道府県名 + 地域名）。例: 東京都 東京地方",
    )
    area_code = serializers.CharField(
        read_only=True,
        help_text="予報区コード（6桁）。例: 130010",
    )
    date = serializers.CharField(
        read_only=True,
        help_text="予報日（YYYY-MM-DD形式）。例: 2025-12-24",
    )
    weather = serializers.CharField(
        read_only=True,
        help_text="天気の説明文。例: 晴れ　夜　くもり",
    )
    weather_code = serializers.CharField(
        read_only=True,
        help_text="天気コード（気象庁定義）。例: 111（晴れ）、200（くもり）",
    )
    temp_min = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="最低気温（℃）。データなしの場合はnull",
    )
    temp_max = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="最高気温（℃）。データなしの場合はnull",
    )
    pop_00_06 = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="降水確率 0時〜6時（%）。データなしの場合はnull",
    )
    pop_06_12 = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="降水確率 6時〜12時（%）。データなしの場合はnull",
    )
    pop_12_18 = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="降水確率 12時〜18時（%）。データなしの場合はnull",
    )
    pop_18_24 = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="降水確率 18時〜24時（%）",
    )
