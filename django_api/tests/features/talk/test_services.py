"""Tests for talk services."""

import time
from unittest.mock import MagicMock, patch

import pytest

from features.talk.exceptions import PlaceholderDataMissingError
from features.talk.models import TalkConfig
from features.talk.services import TalkService
from integrations.langfuse.models import LangfusePromptRef
from integrations.tts.client import TTSResult


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    """Langfuse 接続を切って fallback_text 経由に統一する."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


def _make_refs(db, *, system_text: str, user_text: str):
    sys_ref = LangfusePromptRef.objects.create(
        name=f"talk-service-system-{id(system_text)}",
        langfuse_prompt_name=f"talk-service-system-{id(system_text)}",
        fallback_text=system_text,
    )
    user_ref = LangfusePromptRef.objects.create(
        name=f"talk-service-user-{id(user_text)}",
        langfuse_prompt_name=f"talk-service-user-{id(user_text)}",
        fallback_text=user_text,
    )
    return sys_ref, user_ref


@pytest.fixture
def prompt_refs(db):
    return _make_refs(
        db,
        system_text="system fallback",
        user_text="weather={{weather}} events={{events}} datetime={{datetime}}",
    )


def _refs(prompt_refs):
    return {
        "system_prompt_ref": prompt_refs[0],
        "user_prompt_ref": prompt_refs[1],
    }


@pytest.mark.django_db
class TestTalkService:
    """TalkServiceのテスト"""

    @pytest.fixture
    def mock_weather_response(self):
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
        return "おはようございます、先輩。\n今日は晴れですね。最高気温は10度です。"

    @pytest.fixture
    def config_datetime_only(self, db):
        """datetime のみ使うユーザープロンプトを持つ config."""
        refs = _make_refs(
            db,
            system_text="system fallback",
            user_text="datetime={{datetime}}",
        )
        return TalkConfig.objects.create(
            name="datetime_only",
            display_name="日時のみテスト",
            system_prompt_ref=refs[0],
            user_prompt_ref=refs[1],
        )

    @pytest.fixture
    def config_with_weather(self, db):
        refs = _make_refs(
            db,
            system_text="system fallback",
            user_text="weather={{weather}} datetime={{datetime}}",
        )
        return TalkConfig.objects.create(
            name="with_weather",
            display_name="天気テスト",
            area_code="130010",
            system_prompt_ref=refs[0],
            user_prompt_ref=refs[1],
        )

    @pytest.fixture
    def config_all_placeholders(self, db):
        refs = _make_refs(
            db,
            system_text="system fallback",
            user_text="weather={{weather}} events={{events}} datetime={{datetime}}",
        )
        return TalkConfig.objects.create(
            name="all_placeholders",
            display_name="全プレースホルダーテスト",
            area_code="130010",
            system_prompt_ref=refs[0],
            user_prompt_ref=refs[1],
        )

    @pytest.fixture
    def config_with_tts(self, db):
        refs = _make_refs(
            db,
            system_text="system fallback",
            user_text="datetime={{datetime}}",
        )
        return TalkConfig.objects.create(
            name="with_tts",
            display_name="TTSテスト",
            tts_enabled=True,
            tts_model="test_model",
            tts_style="Happy",
            tts_speed=1.2,
            system_prompt_ref=refs[0],
            user_prompt_ref=refs[1],
        )

    @pytest.fixture
    def config_no_placeholders(self, db):
        refs = _make_refs(
            db,
            system_text="system fallback",
            user_text="プレースホルダーなし",
        )
        return TalkConfig.objects.create(
            name="no_placeholders",
            display_name="プレースホルダー無効",
            system_prompt_ref=refs[0],
            user_prompt_ref=refs[1],
        )

    # 正常系テスト

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_datetime_only(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_datetime_only,
    ):
        """datetime のみ使用時に挨拶が生成される."""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        result = service.synthesize(config=config_datetime_only)

        assert result is not None
        assert result["greeting_text"] == mock_openai_response
        assert "audio_data" not in result
        mock_openai.generate_text.assert_called_once()

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.WeatherClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_with_weather(
        self,
        mock_openai_class,
        mock_weather_class,
        mock_holiday_class,
        mock_weather_response,
        mock_openai_response,
        config_with_weather,
    ):
        """プロンプトに {{weather}} があれば天気APIが呼ばれる."""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_weather = MagicMock()
        mock_weather.get_weather.return_value = mock_weather_response
        mock_weather_class.return_value = mock_weather

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        result = service.synthesize(config=config_with_weather)

        assert result is not None
        assert "greeting_text" in result
        mock_weather.get_weather.assert_called_once_with("130010", 0)

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.WeatherClient")
    @patch("features.talk.services.OutlookMSGraphClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_all_placeholders(
        self,
        mock_openai_class,
        mock_outlook_class,
        mock_weather_class,
        mock_holiday_class,
        mock_weather_response,
        mock_events_response,
        mock_openai_response,
        config_all_placeholders,
    ):
        """全プレースホルダー含むプロンプト時に全APIが呼ばれる."""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_weather = MagicMock()
        mock_weather.get_weather.return_value = mock_weather_response
        mock_weather_class.return_value = mock_weather

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.return_value = mock_events_response
        mock_outlook_class.return_value = mock_outlook

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        result = service.synthesize(config=config_all_placeholders)

        assert result is not None
        assert "greeting_text" in result
        mock_weather.get_weather.assert_called_once()
        mock_outlook.get_calendar_events.assert_called_once()

    @patch("features.talk.services.WeatherClient")
    @patch("features.talk.services.OutlookMSGraphClient")
    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_no_placeholders_calls_no_external_apis(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_outlook_class,
        mock_weather_class,
        mock_openai_response,
        config_no_placeholders,
    ):
        """プロンプトにプレースホルダーが無いときは外部APIを呼ばない."""
        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        result = service.synthesize(config=config_no_placeholders)

        assert result is not None
        assert "greeting_text" in result
        mock_weather_class.return_value.get_weather.assert_not_called()
        mock_outlook_class.return_value.get_calendar_events.assert_not_called()
        mock_holiday_class.return_value.get_holiday_name.assert_not_called()

    # 動的検出テスト

    @patch("features.talk.services.WeatherClient")
    @patch("features.talk.services.OutlookMSGraphClient")
    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_user_prompt_overrides_required_keys(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_outlook_class,
        mock_weather_class,
        mock_openai_response,
        config_no_placeholders,
    ):
        """カスタム user_prompt のプレースホルダーで取得対象が決まる."""
        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        service = TalkService()
        # config は no_placeholders だが user_prompt 側に datetime があるので取得される
        service.synthesize(
            config=config_no_placeholders,
            user_prompt="今日は {{datetime}} です。",
        )

        mock_holiday.get_holiday_name.assert_called_once()
        mock_weather_class.return_value.get_weather.assert_not_called()
        mock_outlook_class.return_value.get_calendar_events.assert_not_called()

    @patch("features.talk.services.WeatherClient")
    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_system_prompt_placeholder_triggers_fetch(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_weather_class,
        mock_weather_response,
        mock_openai_response,
        db,
    ):
        """system_prompt 側の {{weather}} でも天気取得がトリガーされる."""
        refs = _make_refs(
            db,
            system_text="system with {{weather}}",
            user_text="no placeholder",
        )
        config = TalkConfig.objects.create(
            name="sys_with_weather",
            display_name="System に天気",
            area_code="130010",
            system_prompt_ref=refs[0],
            user_prompt_ref=refs[1],
        )

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_weather = MagicMock()
        mock_weather.get_weather.return_value = mock_weather_response
        mock_weather_class.return_value = mock_weather

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        service.synthesize(config=config)

        mock_weather.get_weather.assert_called_once()

    def test_synthesize_weather_requires_area_code(self, db):
        """{{weather}} 含むが area_code 空なら PlaceholderDataMissingError."""
        refs = _make_refs(
            db,
            system_text="system fallback",
            user_text="天気: {{weather}}",
        )
        config = TalkConfig.objects.create(
            name="missing_area",
            display_name="area_code 空",
            area_code="",
            system_prompt_ref=refs[0],
            user_prompt_ref=refs[1],
        )

        service = TalkService()
        with pytest.raises(PlaceholderDataMissingError) as exc_info:
            service.synthesize(config=config)
        assert "area_code" in str(exc_info.value)

    # TTS関連テスト

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    @patch("features.talk.services.TTSClient")
    def test_synthesize_with_tts(
        self,
        mock_tts_class,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_with_tts,
    ):
        """TTS有効時に音声が生成される."""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = TTSResult(
            audio_data=b"fake_wav_data",
            content_type="audio/wav",
            format="wav",
        )
        mock_tts_class.return_value = mock_tts

        service = TalkService()
        result = service.synthesize(config=config_with_tts)

        assert result is not None
        assert result["audio_data"] == b"fake_wav_data"
        assert result["audio_content_type"] == "audio/wav"
        assert result["audio_format"] == "wav"

        mock_tts.synthesize.assert_called_once()
        call_kwargs = mock_tts.synthesize.call_args.kwargs
        assert call_kwargs["text"] == mock_openai_response
        assert call_kwargs["model"] == "test_model"
        assert call_kwargs["style"] == "Happy"
        assert call_kwargs["speed"] == 1.2
        assert call_kwargs["format"] == "wav"

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_without_tts(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_datetime_only,
    ):
        """TTS無効時は音声データがない."""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        result = service.synthesize(config=config_datetime_only)

        assert "audio_data" not in result

    # エラーハンドリングテスト

    @patch("features.talk.services.WeatherClient")
    def test_synthesize_weather_error(
        self,
        mock_weather_class,
        config_with_weather,
    ):
        """天気API失敗時にエラーが発生する."""
        from integrations.weather.exceptions import WeatherNetworkError

        mock_weather = MagicMock()
        mock_weather.get_weather.side_effect = WeatherNetworkError("Network error")
        mock_weather_class.return_value = mock_weather

        service = TalkService()

        with pytest.raises(WeatherNetworkError):
            service.synthesize(config=config_with_weather)

    # プロンプト変数構築テスト

    def test_build_prompt_variables_includes_json_strings(self):
        """_build_prompt_variables は JSON 文字列を返す."""
        service = TalkService()

        data = {
            "weather": {"area_name": "東京地方"},
            "datetime": {"date": "2025-01-11"},
        }
        variables = service._build_prompt_variables(data)

        assert "東京地方" in variables["weather"]
        assert "2025-01-11" in variables["datetime"]
        assert variables["events"] == ""  # 欠落キーは空文字

    def test_build_prompt_variables_empty_data(self):
        """データが空の場合、変数はすべて空文字."""
        service = TalkService()

        variables = service._build_prompt_variables({})

        assert variables == {"weather": "", "events": "", "datetime": ""}

    # 並列実行テスト

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.WeatherClient")
    @patch("features.talk.services.OutlookMSGraphClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_parallel_execution(
        self,
        mock_openai_class,
        mock_outlook_class,
        mock_weather_class,
        mock_holiday_class,
        mock_weather_response,
        mock_events_response,
        mock_openai_response,
        config_all_placeholders,
    ):
        """API呼び出しが並列で実行される."""

        def slow_weather(*args, **kwargs):
            time.sleep(0.1)
            return mock_weather_response

        def slow_events(*args, **kwargs):
            time.sleep(0.1)
            return mock_events_response

        def slow_datetime(*args, **kwargs):
            time.sleep(0.1)
            return None

        mock_weather = MagicMock()
        mock_weather.get_weather.side_effect = slow_weather
        mock_weather_class.return_value = mock_weather

        mock_outlook = MagicMock()
        mock_outlook.get_calendar_events.side_effect = slow_events
        mock_outlook_class.return_value = mock_outlook

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.side_effect = slow_datetime
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        start = time.time()
        result = service.synthesize(config=config_all_placeholders)
        elapsed = time.time() - start

        assert result is not None

        # 並列実行なら0.2秒未満（直列なら0.3秒以上）
        assert elapsed < 0.25, f"並列実行されていません: {elapsed:.2f}秒"

    # user_prompt 指定テスト

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_with_custom_user_prompt_expands_placeholders(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_datetime_only,
    ):
        """user_prompt 指定時: {{datetime}} 等のプレースホルダーが展開される."""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        custom_prompt = "今日は {{datetime}} です。"
        service.synthesize(
            config=config_datetime_only,
            user_prompt=custom_prompt,
        )

        llm_call_kwargs = mock_openai.generate_text.call_args.kwargs
        sent_prompt = llm_call_kwargs["prompt"]
        # {{datetime}} は JSON 化された日時情報に置換される
        assert "{{datetime}}" not in sent_prompt
        assert "day_of_week" in sent_prompt

    # 祝日テスト

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_with_holiday(
        self,
        mock_openai_class,
        mock_holiday_class,
        mock_openai_response,
        config_datetime_only,
    ):
        """祝日がある場合も正常に動作し、プロンプトに祝日名が含まれる."""
        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = "元日"
        mock_holiday_class.return_value = mock_holiday

        mock_openai = MagicMock()
        mock_openai.generate_text.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai

        service = TalkService()
        result = service.synthesize(config=config_datetime_only)

        assert result is not None
        call_args = mock_openai.generate_text.call_args
        prompt_sent = call_args.kwargs["prompt"]
        assert "元日" in prompt_sent
