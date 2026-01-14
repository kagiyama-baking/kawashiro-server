"""Tests for greeting services."""

from unittest.mock import MagicMock, patch

import pytest

from greeting.services import EveningGreetingService, MorningGreetingService


class TestMorningGreetingService:
    """MorningGreetingServiceのテスト"""

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
        return {
            "start_date": "2025-12-24",
            "end_date": "2025-12-24",
            "count": 1,
            "events": [
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
            ],
        }

    @pytest.fixture
    def mock_openai_response(self):
        """OpenAI APIのモックレスポンス"""
        return "おはようございます、先輩。\n今日は晴れですね。最高気温は10度、最低気温は4度です。\n午後から雨が降るかもしれないので、傘を持っていくといいですよ。\n今日も頑張ってくださいね。"

    @pytest.fixture
    def system_prompt(self):
        """テスト用システムプロンプト"""
        return "テスト用システムプロンプト"

    @pytest.fixture
    def user_prompt_template(self):
        """テスト用ユーザープロンプトテンプレート"""
        return "朝の挨拶: {{weather}} {{events}} {{datetime}}"

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OutlookMSGraphClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_success(
        self,
        mock_openai_class,
        mock_outlook_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_events_response,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """正常系: 挨拶が生成される"""
        # モックの設定
        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.return_value = mock_events_response["events"]
        mock_outlook_class.return_value = mock_outlook

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        # サービス実行
        service = MorningGreetingService()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
        )

        # 検証
        assert result is not None
        assert "greeting_text" in result
        assert result["greeting_text"] == mock_openai_response

        # 各APIが呼ばれたことを確認
        mock_jma.get_weather.assert_called_once_with("130010", 0)
        mock_outlook.get_calendar_events.assert_called_once()
        mock_openai.generate_text.assert_called_once()

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OutlookMSGraphClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_with_empty_events(
        self,
        mock_openai_class,
        mock_outlook_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """予定がない場合でも正常に動作する"""
        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.return_value = []  # 予定なし
        mock_outlook_class.return_value = mock_outlook

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = MorningGreetingService()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
        )

        assert result is not None
        assert "greeting_text" in result

    @patch("greeting.services.JMAWeatherClient")
    def test_generate_greeting_weather_error(
        self,
        mock_jma_class,
        system_prompt,
        user_prompt_template,
    ):
        """天気予報API失敗時にエラーが発生する"""
        from weather.exceptions import JMANetworkError

        mock_jma = MagicMock()
        mock_jma.get_weather.side_effect = JMANetworkError("Network error")
        mock_jma_class.return_value = mock_jma

        service = MorningGreetingService()

        with pytest.raises(JMANetworkError):
            service.generate_greeting(
                area_code="130010",
                system_prompt=system_prompt,
                user_prompt=user_prompt_template,
            )

    def test_build_user_prompt(self):
        """ユーザープロンプトが正しく構築される"""
        service = MorningGreetingService()

        template = "朝の挨拶: {{weather}} {{events}}"
        weather_data = {"area_name": "東京地方", "weather": "晴れ"}
        events_data = [{"subject": "会議"}]

        prompt = service._build_user_prompt(template, weather_data, events_data)

        assert "朝の挨拶" in prompt
        assert "東京地方" in prompt
        assert "会議" in prompt

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OutlookMSGraphClient")
    @patch("greeting.services.OpenAIClient")
    @patch("greeting.services.TTSClient")
    def test_generate_greeting_with_tts(
        self,
        mock_tts_class,
        mock_openai_class,
        mock_outlook_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_events_response,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """TTS付きで挨拶が生成される"""
        # モックの設定
        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.return_value = mock_events_response["events"]
        mock_outlook_class.return_value = mock_outlook

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"RIFF....WAVEfmt "
        mock_tts_class.return_value = mock_tts

        # TTS付きで実行（モデルから取得する全キーが必要）
        tts_options = {
            "model": "test_model",
            "style": "Happy",
            "style_weight": 1.0,
            "speed": 1.2,
            "sdp_ratio": 0.2,
            "noise_scale": 0.6,
            "noise_scale_w": 0.8,
        }

        service = MorningGreetingService()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
            tts_options=tts_options,
        )

        # 検証
        assert result is not None
        assert "greeting_text" in result
        assert "audio_data" in result
        assert result["audio_data"] == b"RIFF....WAVEfmt "

        # TTSが呼ばれたことを確認
        mock_tts.synthesize.assert_called_once()
        call_kwargs = mock_tts.synthesize.call_args.kwargs
        assert call_kwargs["text"] == mock_openai_response
        assert call_kwargs["model"] == "test_model"
        assert call_kwargs["style"] == "Happy"
        assert call_kwargs["speed"] == 1.2

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OutlookMSGraphClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_without_tts(
        self,
        mock_openai_class,
        mock_outlook_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_events_response,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """TTS無しの場合は音声データがない"""
        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.return_value = mock_events_response["events"]
        mock_outlook_class.return_value = mock_outlook

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        # TTS無しで実行
        service = MorningGreetingService()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
            tts_options=None,
        )

        # 検証
        assert result is not None
        assert "greeting_text" in result
        assert "audio_data" not in result

    def test_build_user_prompt_escapes_template_markers(self):
        """ユーザー入力がテンプレートマーカーを含んでも安全に処理される"""
        service = MorningGreetingService()

        # テンプレートマーカーを含むテンプレート
        template = "挨拶: {{weather}}"
        # 天気データにテンプレートマーカーが含まれる場合
        weather_data = {"area_name": "東京地方", "note": "{{events}}は無視"}
        events_data = []

        prompt = service._build_user_prompt(template, weather_data, events_data)

        # データ内の{{events}}がそのまま残っている（テンプレート置換されていない）
        assert "{{events}}は無視" in prompt

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
        system_prompt,
        user_prompt_template,
    ):
        """API呼び出しが並列で実行される（パフォーマンステスト）"""
        import time

        call_times = []

        def slow_weather(*args, **kwargs):
            call_times.append(("weather", time.time()))
            time.sleep(0.1)
            return mock_weather_response

        def slow_events(*args, **kwargs):
            call_times.append(("events", time.time()))
            time.sleep(0.1)
            return mock_events_response["events"]

        def slow_datetime(*args, **kwargs):
            call_times.append(("datetime", time.time()))
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

        service = MorningGreetingService()
        start = time.time()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
        )
        elapsed = time.time() - start

        assert result is not None

        # 並列実行なら0.2秒未満（直列なら0.3秒以上）
        # 許容誤差を考慮して0.25秒未満を期待
        assert elapsed < 0.25, f"並列実行されていません: {elapsed:.2f}秒かかりました"

    def test_build_user_prompt_with_datetime(self):
        """{{datetime}}プレースホルダーが正しく置換される"""
        service = MorningGreetingService()

        template = "日時: {{datetime}} 天気: {{weather}}"
        weather_data = {"area_name": "東京地方", "weather": "晴れ"}
        events_data = []
        datetime_data = {
            "date": "2025-01-11",
            "time": "09:30:00",
            "day_of_week": "Saturday",
            "day_of_week_ja": "土曜日",
            "holiday_name": None,
        }

        prompt = service._build_user_prompt(
            template, weather_data, events_data, datetime_data
        )

        assert "日時" in prompt
        assert "2025-01-11" in prompt
        assert "土曜日" in prompt
        assert "東京地方" in prompt

    def test_build_user_prompt_with_datetime_holiday(self):
        """祝日の場合も{{datetime}}プレースホルダーが正しく置換される"""
        service = MorningGreetingService()

        template = "{{datetime}}"
        weather_data = {}
        events_data = []
        datetime_data = {
            "date": "2025-01-01",
            "time": "08:00:00",
            "day_of_week": "Wednesday",
            "day_of_week_ja": "水曜日",
            "holiday_name": "元日",
        }

        prompt = service._build_user_prompt(
            template, weather_data, events_data, datetime_data
        )

        assert "元日" in prompt
        assert "2025-01-01" in prompt
        assert "水曜日" in prompt

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OutlookMSGraphClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_includes_datetime(
        self,
        mock_openai_class,
        mock_outlook_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_events_response,
        mock_openai_response,
        system_prompt,
    ):
        """generate_greetingが日時情報を含む"""
        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.return_value = mock_events_response["events"]
        mock_outlook_class.return_value = mock_outlook

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        # {{datetime}}を含むテンプレート
        user_prompt = "日時: {{datetime}} 天気: {{weather}} 予定: {{events}}"

        service = MorningGreetingService()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        assert result is not None
        assert "greeting_text" in result

        # OpenAI APIに渡されたプロンプトを確認
        call_args = mock_openai.generate_text.call_args
        prompt_sent = call_args.kwargs["prompt"]

        # 日時情報が含まれていることを確認
        assert "date" in prompt_sent
        assert "day_of_week" in prompt_sent


class TestEveningGreetingService:
    """EveningGreetingServiceのテスト"""

    @pytest.fixture
    def mock_openai_response(self):
        """OpenAI APIのモックレスポンス"""
        return "おつかれさまでした、先輩。\n今日も一日お疲れ様でした。\nゆっくり休んでくださいね。"

    @pytest.fixture
    def system_prompt(self):
        """テスト用システムプロンプト"""
        return "テスト用システムプロンプト"

    @pytest.fixture
    def user_prompt_template(self):
        """テスト用ユーザープロンプトテンプレート"""
        return "夜の挨拶: {{datetime}}"

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_success(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """正常系: 挨拶が生成される"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        # サービス実行
        service = EveningGreetingService()
        result = service.generate_greeting(
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
        )

        # 検証
        assert result is not None
        assert "greeting_text" in result
        assert result["greeting_text"] == mock_openai_response

        # OpenAIが呼ばれたことを確認
        mock_openai.generate_text.assert_called_once()

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.OpenAIClient")
    @patch("greeting.services.TTSClient")
    def test_generate_greeting_with_tts(
        self,
        mock_tts_class,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """TTS付きで挨拶が生成される"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"RIFF....WAVEfmt "
        mock_tts_class.return_value = mock_tts

        tts_options = {
            "model": "test_model",
            "style": "Happy",
            "style_weight": 1.0,
            "speed": 1.2,
            "sdp_ratio": 0.2,
            "noise_scale": 0.6,
            "noise_scale_w": 0.8,
        }

        service = EveningGreetingService()
        result = service.generate_greeting(
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
            tts_options=tts_options,
        )

        # 検証
        assert result is not None
        assert "greeting_text" in result
        assert "audio_data" in result
        assert result["audio_data"] == b"RIFF....WAVEfmt "

        # TTSが呼ばれたことを確認
        mock_tts.synthesize.assert_called_once()

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_without_tts(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """TTS無しの場合は音声データがない"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = EveningGreetingService()
        result = service.generate_greeting(
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
            tts_options=None,
        )

        # 検証
        assert result is not None
        assert "greeting_text" in result
        assert "audio_data" not in result

    def test_build_user_prompt(self):
        """ユーザープロンプトが正しく構築される"""
        service = EveningGreetingService()

        template = "夜の挨拶: {{datetime}}"
        datetime_data = {
            "date": "2025-01-11",
            "time": "21:30:00",
            "day_of_week": "Saturday",
            "day_of_week_ja": "土曜日",
            "holiday_name": None,
        }

        prompt = service._build_user_prompt(template, datetime_data)

        assert "夜の挨拶" in prompt
        assert "2025-01-11" in prompt
        assert "土曜日" in prompt

    def test_build_user_prompt_with_holiday(self):
        """祝日の場合もプレースホルダーが正しく置換される"""
        service = EveningGreetingService()

        template = "{{datetime}}"
        datetime_data = {
            "date": "2025-01-01",
            "time": "21:00:00",
            "day_of_week": "Wednesday",
            "day_of_week_ja": "水曜日",
            "holiday_name": "元日",
        }

        prompt = service._build_user_prompt(template, datetime_data)

        assert "元日" in prompt
        assert "2025-01-01" in prompt
        assert "水曜日" in prompt

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_includes_datetime(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        system_prompt,
    ):
        """generate_greetingが日時情報を含む"""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        user_prompt = "日時: {{datetime}}"

        service = EveningGreetingService()
        result = service.generate_greeting(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        assert result is not None
        assert "greeting_text" in result

        # OpenAI APIに渡されたプロンプトを確認
        call_args = mock_openai.generate_text.call_args
        prompt_sent = call_args.kwargs["prompt"]

        # 日時情報が含まれていることを確認
        assert "date" in prompt_sent
        assert "day_of_week" in prompt_sent


class TestWelcomeHomeGreetingService:
    """WelcomeHomeGreetingServiceのテスト"""

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
    def mock_openai_response(self):
        """OpenAI APIのモックレスポンス"""
        return "おかえりなさい、先輩。\n今日はお疲れ様でした。\n外は晴れていて気持ちいいですね。"

    @pytest.fixture
    def system_prompt(self):
        """テスト用システムプロンプト"""
        return "テスト用システムプロンプト"

    @pytest.fixture
    def user_prompt_template(self):
        """テスト用ユーザープロンプトテンプレート"""
        return "おかえりの挨拶: {{datetime}} {{weather}}"

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_success(
        self,
        mock_openai_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """正常系: 挨拶が生成される"""
        from greeting.services import WelcomeHomeGreetingService

        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = WelcomeHomeGreetingService()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
        )

        assert result is not None
        assert "greeting_text" in result
        assert result["greeting_text"] == mock_openai_response

        mock_jma.get_weather.assert_called_once_with("130010", 0)
        mock_openai.generate_text.assert_called_once()

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OpenAIClient")
    @patch("greeting.services.TTSClient")
    def test_generate_greeting_with_tts(
        self,
        mock_tts_class,
        mock_openai_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """TTS付きで挨拶が生成される"""
        from greeting.services import WelcomeHomeGreetingService

        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"RIFF....WAVEfmt "
        mock_tts_class.return_value = mock_tts

        tts_options = {
            "model": "test_model",
            "style": "Happy",
            "style_weight": 1.0,
            "speed": 1.2,
            "sdp_ratio": 0.2,
            "noise_scale": 0.6,
            "noise_scale_w": 0.8,
        }

        service = WelcomeHomeGreetingService()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
            tts_options=tts_options,
        )

        assert result is not None
        assert "greeting_text" in result
        assert "audio_data" in result
        assert result["audio_data"] == b"RIFF....WAVEfmt "

        mock_tts.synthesize.assert_called_once()

    @patch("greeting.services.HolidayClient")
    @patch("greeting.services.JMAWeatherClient")
    @patch("greeting.services.OpenAIClient")
    def test_generate_greeting_without_tts(
        self,
        mock_openai_class,
        mock_jma_class,
        mock_holiday_class,
        mock_weather_response,
        mock_openai_response,
        system_prompt,
        user_prompt_template,
    ):
        """TTS無しの場合は音声データがない"""
        from greeting.services import WelcomeHomeGreetingService

        mock_jma = MagicMock()
        mock_jma.get_weather.return_value = mock_weather_response
        mock_jma_class.return_value = mock_jma

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = WelcomeHomeGreetingService()
        result = service.generate_greeting(
            area_code="130010",
            system_prompt=system_prompt,
            user_prompt=user_prompt_template,
            tts_options=None,
        )

        assert result is not None
        assert "greeting_text" in result
        assert "audio_data" not in result

    def test_build_user_prompt(self):
        """ユーザープロンプトが正しく構築される"""
        from greeting.services import WelcomeHomeGreetingService

        service = WelcomeHomeGreetingService()

        template = "おかえりの挨拶: {{datetime}} {{weather}}"
        weather_data = {"area_name": "東京地方", "weather": "晴れ"}
        datetime_data = {
            "date": "2025-01-11",
            "time": "18:30:00",
            "day_of_week": "Saturday",
            "day_of_week_ja": "土曜日",
            "holiday_name": None,
        }

        prompt = service._build_user_prompt(template, weather_data, datetime_data)

        assert "おかえりの挨拶" in prompt
        assert "東京地方" in prompt
        assert "2025-01-11" in prompt
        assert "土曜日" in prompt

    @patch("greeting.services.JMAWeatherClient")
    def test_generate_greeting_weather_error(
        self,
        mock_jma_class,
        system_prompt,
        user_prompt_template,
    ):
        """天気予報API失敗時にエラーが発生する"""
        from greeting.services import WelcomeHomeGreetingService
        from weather.exceptions import JMANetworkError

        mock_jma = MagicMock()
        mock_jma.get_weather.side_effect = JMANetworkError("Network error")
        mock_jma_class.return_value = mock_jma

        service = WelcomeHomeGreetingService()

        with pytest.raises(JMANetworkError):
            service.generate_greeting(
                area_code="130010",
                system_prompt=system_prompt,
                user_prompt=user_prompt_template,
            )
