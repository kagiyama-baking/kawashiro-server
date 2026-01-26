"""Tests for greeting services."""

import time
from unittest.mock import MagicMock, patch

import pytest

from greeting.models import GreetingConfig
from greeting.services import GreetingService


@pytest.mark.django_db
class TestGreetingService:
    """GreetingServiceのテスト"""

    @pytest.fixture
    def mock_weather_response(self):
        """天気予報APIのモックレスポンス"""
        return {
            "area_name": "東京都 東京地方",
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

    @pytest.fixture
    def mock_events_response(self):
        """予定取得APIのモックレスポンス"""
        return [
            {
                "id": "AAMkAGI...",
                "subject": "チーム定例",
                "start": {
                    "dateTime": "2025-12-24T10:00:00",
                    "timeZone": "Tokyo Standard Time",
                },
                "end": {
                    "dateTime": "2025-12-24T11:00:00",
                    "timeZone": "Tokyo Standard Time",
                },
                "location": "会議室A",
                "is_all_day": False,
            }
        ]

    @pytest.fixture
    def mock_openai_response(self):
        """OpenAI APIのモックレスポンス"""
        return "おはようございます、先輩。\n今日は晴れですね。最高気温は10度です。"

    @pytest.fixture
    def config_datetime_only(self):
        """日時のみ使用の設定"""
        return GreetingConfig.objects.create(
            name="datetime_only",
            display_name="日時のみテスト",
            use_weather=False,
            use_events=False,
            use_datetime=True,
            system_prompt="テスト用システムプロンプト",
        )

    @pytest.fixture
    def config_with_weather(self):
        """天気使用の設定"""
        return GreetingConfig.objects.create(
            name="with_weather",
            display_name="天気テスト",
            use_weather=True,
            use_events=False,
            use_datetime=True,
            area_code="130010",
            system_prompt="テスト用システムプロンプト",
        )

    @pytest.fixture
    def config_all_placeholders(self):
        """全プレースホルダー使用の設定"""
        return GreetingConfig.objects.create(
            name="all_placeholders",
            display_name="全プレースホルダーテスト",
            use_weather=True,
            use_events=True,
            use_datetime=True,
            area_code="130010",
            system_prompt="テスト用システムプロンプト",
        )

    @pytest.fixture
    def config_with_tts(self):
        """TTS有効の設定"""
        return GreetingConfig.objects.create(
            name="with_tts",
            display_name="TTSテスト",
            use_weather=False,
            use_events=False,
            use_datetime=True,
            system_prompt="テスト用システムプロンプト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_speed=1.2,
        )

    @pytest.fixture
    def config_no_placeholders(self):
        """プレースホルダー無効の設定"""
        return GreetingConfig.objects.create(
            name="no_placeholders",
            display_name="プレースホルダー無効",
            use_weather=False,
            use_events=False,
            use_datetime=False,
            system_prompt="テスト用システムプロンプト",
        )

    # 正常系テスト

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_datetime_only(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_datetime_only,
    ):
        """日時のみ使用時に挨拶が生成される"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = GreetingService()
        result = service.generate_greeting(
            config=config_datetime_only,
            user_prompt="今日は{{datetime}}です。挨拶してください。",
        )

        assert result is not None
        assert "greeting_text" in result
        assert result["greeting_text"] == mock_openai_response
        assert "audio_data" not in result

        mock_openai.generate_text.assert_called_once()

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_with_weather(
        self,
        mock_openai_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_openai_response,
        config_with_weather,
    ):
        """天気使用時に天気APIが呼ばれる"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = GreetingService()
        result = service.generate_greeting(
            config=config_with_weather,
            user_prompt="天気: {{weather}} 日時: {{datetime}}",
        )

        assert result is not None
        assert "greeting_text" in result
        mock_jma.get_weather.assert_called_once_with("130010", 0)

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OutlookMSGraphClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_all_placeholders(
        self,
        mock_openai_class,
        mock_outlook_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_events_response,
        mock_openai_response,
        config_all_placeholders,
    ):
        """全プレースホルダー使用時に全APIが呼ばれる"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.return_value = mock_events_response
        mock_outlook_class.return_value = mock_outlook

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = GreetingService()
        result = service.generate_greeting(
            config=config_all_placeholders,
            user_prompt="{{weather}} {{events}} {{datetime}}",
        )

        assert result is not None
        assert "greeting_text" in result
        mock_jma.get_weather.assert_called_once()
        mock_outlook.get_calendar_events.assert_called_once()

    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_no_placeholders(
        self,
        mock_openai_class,
        mock_openai_response,
        config_no_placeholders,
    ):
        """プレースホルダー無効時はAPIを呼ばない"""
        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = GreetingService()
        result = service.generate_greeting(
            config=config_no_placeholders,
            user_prompt="挨拶してください。",
        )

        assert result is not None
        assert "greeting_text" in result

    # TTS関連テスト

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.OpenAIClient")
    @patch("greeting.services.TTSClient")
    def test_generate_greeting_with_tts(
        self,
        mock_tts_class,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_with_tts,
    ):
        """TTS有効時に音声が生成される"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"RIFF....WAVEfmt "
        mock_tts_class.return_value = mock_tts

        service = GreetingService()
        result = service.generate_greeting(
            config=config_with_tts,
            user_prompt="{{datetime}}",
        )

        assert result is not None
        assert "greeting_text" in result
        assert "audio_data" in result
        assert result["audio_data"] == b"RIFF....WAVEfmt "

        mock_tts.synthesize.assert_called_once()
        call_kwargs = mock_tts.synthesize.call_args.kwargs
        assert call_kwargs["text"] == mock_openai_response
        assert call_kwargs["model"] == "test_model"
        assert call_kwargs["style"] == "Happy"
        assert call_kwargs["speed"] == 1.2

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_without_tts(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_datetime_only,
    ):
        """TTS無効時は音声データがない"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = GreetingService()
        result = service.generate_greeting(
            config=config_datetime_only,
            user_prompt="{{datetime}}",
        )

        assert result is not None
        assert "greeting_text" in result
        assert "audio_data" not in result

    # エラーハンドリングテスト

    @patch("greeting.services.JMAWeatherClient")
    def test_generate_greeting_weather_error(
        self,
        mock_jma_class,
        config_with_weather,
    ):
        """天気API失敗時にエラーが発生する"""
        from weather.exceptions import JMANetworkError

        mock_jma = MagicMock()
        mock_jma.get_weather.side_effect = JMANetworkError("Network error")
        mock_jma_class.return_value = mock_jma

        service = GreetingService()

        with pytest.raises(JMANetworkError):
            service.generate_greeting(
                config=config_with_weather,
                user_prompt="{{weather}}",
            )

    # プロンプト構築テスト

    def test_build_user_prompt_replaces_placeholders(self):
        """_build_user_promptがプレースホルダーを置換する"""
        service = GreetingService()

        template = "天気: {{weather}} 日時: {{datetime}}"
        data = {
            "weather": {"area_name": "東京地方", "weather": "晴れ"},
            "datetime": {"date": "2025-01-11", "day_of_week_ja": "土曜日"},
        }

        prompt = service._build_user_prompt(template, data)

        assert "天気" in prompt
        assert "東京地方" in prompt
        assert "2025-01-11" in prompt

    def test_build_user_prompt_escapes_template_markers(self):
        """データ内のテンプレートマーカーは置換されない"""
        service = GreetingService()

        template = "{{weather}}"
        data = {
            "weather": {"note": "{{events}}は無視"},
        }

        prompt = service._build_user_prompt(template, data)

        # データ内の{{events}}がそのまま残っている
        assert "{{events}}は無視" in prompt

    def test_build_user_prompt_no_data(self):
        """データがない場合はテンプレートがそのまま返る"""
        service = GreetingService()

        template = "挨拶してください"
        data = {}

        prompt = service._build_user_prompt(template, data)

        assert prompt == "挨拶してください"

    # 並列実行テスト

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OutlookMSGraphClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_parallel_execution(
        self,
        mock_openai_class,
        mock_outlook_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_events_response,
        mock_openai_response,
        config_all_placeholders,
    ):
        """API呼び出しが並列で実行される"""

        def slow_weather(*args, **kwargs):
            time.sleep(0.1)
            return mock_weather_response

        def slow_events(*args, **kwargs):
            time.sleep(0.1)
            return mock_events_response

        def slow_datetime(*args, **kwargs):
            time.sleep(0.1)
            return None

        mock_jma = MagicMock()
        mock_jma.get_weather.side_effect = slow_weather
        mock_jma_class.return_value = mock_jma

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.side_effect = slow_events
        mock_outlook_class.return_value = mock_outlook

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.side_effect = slow_datetime
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = GreetingService()
        start = time.time()
        result = service.generate_greeting(
            config=config_all_placeholders,
            user_prompt="{{weather}} {{events}} {{datetime}}",
        )
        elapsed = time.time() - start

        assert result is not None

        # 並列実行なら0.2秒未満（直列なら0.3秒以上）
        assert elapsed < 0.25, f"並列実行されていません: {elapsed:.2f}秒かかりました"

    # 祝日テスト

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_with_holiday(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_datetime_only,
    ):
        """祝日がある場合も正常に動作する"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = "元日"
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = GreetingService()
        result = service.generate_greeting(
            config=config_datetime_only,
            user_prompt="{{datetime}}",
        )

        assert result is not None
        assert "greeting_text" in result

        # OpenAI APIに渡されたプロンプトに祝日情報が含まれる
        call_args = mock_openai.generate_text.call_args
        prompt_sent = call_args.kwargs["prompt"]
        assert "元日" in prompt_sent
