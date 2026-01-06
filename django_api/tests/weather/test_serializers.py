"""Tests for weather serializers."""

from weather.serializers import WeatherRequestSerializer, WeatherResponseSerializer


class TestWeatherRequestSerializer:
    """Tests for WeatherRequestSerializer."""

    def test_valid_area_code_only(self):
        """予報区コードのみの場合、デフォルトでday=0（今日）が設定される"""
        data = {"area_code": "130010"}
        serializer = WeatherRequestSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["area_code"] == "130010"
        assert serializer.validated_data["day"] == 0

    def test_valid_area_code_with_day_today(self):
        """day=0（今日）を指定した場合"""
        data = {"area_code": "130010", "day": 0}
        serializer = WeatherRequestSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["day"] == 0

    def test_valid_area_code_with_day_tomorrow(self):
        """day=1（明日）を指定した場合"""
        data = {"area_code": "130010", "day": 1}
        serializer = WeatherRequestSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["day"] == 1

    def test_valid_area_code_with_day_after_tomorrow(self):
        """day=2（明後日）を指定した場合"""
        data = {"area_code": "130010", "day": 2}
        serializer = WeatherRequestSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["day"] == 2

    def test_missing_area_code_is_invalid(self):
        """予報区コードが無い場合は無効"""
        data = {"day": 0}
        serializer = WeatherRequestSerializer(data=data)

        assert not serializer.is_valid()
        assert "area_code" in serializer.errors

    def test_invalid_day_negative(self):
        """dayが負の値の場合は無効"""
        data = {"area_code": "130010", "day": -1}
        serializer = WeatherRequestSerializer(data=data)

        assert not serializer.is_valid()
        assert "day" in serializer.errors

    def test_invalid_day_too_large(self):
        """dayが3以上の場合は無効（0, 1, 2のみ有効）"""
        data = {"area_code": "130010", "day": 3}
        serializer = WeatherRequestSerializer(data=data)

        assert not serializer.is_valid()
        assert "day" in serializer.errors

    def test_area_code_must_be_string(self):
        """予報区コードは文字列である必要がある"""
        data = {"area_code": "130010"}
        serializer = WeatherRequestSerializer(data=data)

        assert serializer.is_valid()
        assert isinstance(serializer.validated_data["area_code"], str)


class TestWeatherResponseSerializer:
    """Tests for WeatherResponseSerializer."""

    def test_serialize_complete_weather_data(self):
        """完全な天気データをシリアライズできる"""
        data = {
            "area_name": "東京地方",
            "area_code": "130010",
            "date": "2025-12-24",
            "weather": "晴れ　夜　くもり",
            "weather_code": "111",
            "temp_min": 4,
            "temp_max": 10,
            "pop_00_06": 10,
            "pop_06_12": 20,
            "pop_12_18": 30,
            "pop_18_24": 40,
        }
        serializer = WeatherResponseSerializer(data)

        assert serializer.data["area_name"] == "東京地方"
        assert serializer.data["area_code"] == "130010"
        assert serializer.data["date"] == "2025-12-24"
        assert serializer.data["weather"] == "晴れ　夜　くもり"
        assert serializer.data["weather_code"] == "111"
        assert serializer.data["temp_min"] == 4
        assert serializer.data["temp_max"] == 10
        assert serializer.data["pop_00_06"] == 10
        assert serializer.data["pop_06_12"] == 20
        assert serializer.data["pop_12_18"] == 30
        assert serializer.data["pop_18_24"] == 40

    def test_serialize_with_null_temperatures(self):
        """気温がNullの場合もシリアライズできる"""
        data = {
            "area_name": "東京地方",
            "area_code": "130010",
            "date": "2025-12-24",
            "weather": "晴れ",
            "weather_code": "100",
            "temp_min": None,
            "temp_max": None,
            "pop_00_06": None,
            "pop_06_12": None,
            "pop_12_18": None,
            "pop_18_24": None,
        }
        serializer = WeatherResponseSerializer(data)

        assert serializer.data["temp_min"] is None
        assert serializer.data["temp_max"] is None
        assert serializer.data["pop_00_06"] is None

    def test_serialize_with_partial_pop_data(self):
        """部分的な降水確率データもシリアライズできる"""
        data = {
            "area_name": "東京地方",
            "area_code": "130010",
            "date": "2025-12-24",
            "weather": "晴れ",
            "weather_code": "100",
            "temp_min": 5,
            "temp_max": 15,
            "pop_00_06": None,
            "pop_06_12": 10,
            "pop_12_18": 20,
            "pop_18_24": 30,
        }
        serializer = WeatherResponseSerializer(data)

        assert serializer.data["pop_00_06"] is None
        assert serializer.data["pop_06_12"] == 10
