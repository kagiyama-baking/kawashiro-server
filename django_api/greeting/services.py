"""Services for greeting app."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any

from django.utils import timezone

from llm_client.openai_client import OpenAIClient
from msgraph_client import OutlookMSGraphClient
from tts.client import TTSClient
from weather.jma_client import JMAWeatherClient

from .holiday_client import HolidayClient

# 曜日の日本語マッピング
DAY_OF_WEEK_JA = {
    "Monday": "月曜日",
    "Tuesday": "火曜日",
    "Wednesday": "水曜日",
    "Thursday": "木曜日",
    "Friday": "金曜日",
    "Saturday": "土曜日",
    "Sunday": "日曜日",
}

logger = logging.getLogger(__name__)


class MorningGreetingService:
    """朝の挨拶生成サービス."""

    def __init__(self):
        """サービスを初期化."""
        self._jma_client = None
        self._outlook_client = None
        self._openai_client = None
        self._tts_client = None
        self._holiday_client = None

    @property
    def jma_client(self) -> JMAWeatherClient:
        """JMAクライアントを取得（遅延初期化）."""
        if self._jma_client is None:
            self._jma_client = JMAWeatherClient()
        return self._jma_client

    @property
    def outlook_client(self) -> OutlookMSGraphClient:
        """Outlookクライアントを取得（遅延初期化）."""
        if self._outlook_client is None:
            self._outlook_client = OutlookMSGraphClient()
        return self._outlook_client

    @property
    def openai_client(self) -> OpenAIClient:
        """OpenAIクライアントを取得（遅延初期化）."""
        if self._openai_client is None:
            self._openai_client = OpenAIClient()
        return self._openai_client

    @property
    def tts_client(self) -> TTSClient:
        """TTSクライアントを取得（遅延初期化）."""
        if self._tts_client is None:
            self._tts_client = TTSClient()
        return self._tts_client

    @property
    def holiday_client(self) -> HolidayClient:
        """祝日クライアントを取得（遅延初期化）."""
        if self._holiday_client is None:
            self._holiday_client = HolidayClient()
        return self._holiday_client

    def generate_greeting(
        self,
        area_code: str,
        system_prompt: str,
        user_prompt: str,
        tts_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """朝の挨拶を生成.

        Args:
            area_code: 予報区コード
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプトテンプレート
            tts_options: TTS音声合成オプション

        Returns:
            生成結果を含むdict

        Raises:
            JMANetworkError: 天気予報API接続エラー
            JMATimeoutError: 天気予報APIタイムアウト
            OpenAITimeoutError: OpenAI APIタイムアウト
            OpenAIAPIError: OpenAI API接続エラー
        """
        logger.info("朝の挨拶を生成: area_code=%s", area_code)

        # 外部API呼び出しを並列実行
        today = date.today()

        def fetch_weather():
            return self.jma_client.get_weather(area_code, 0)

        def fetch_events():
            return self.outlook_client.get_calendar_events(
                start_date=today,
                end_date=today,
            )

        def fetch_datetime():
            return self._get_datetime_info()

        with ThreadPoolExecutor(max_workers=3) as executor:
            weather_future = executor.submit(fetch_weather)
            events_future = executor.submit(fetch_events)
            datetime_future = executor.submit(fetch_datetime)

            # 結果を取得（例外があればここで再送出される）
            weather_data = weather_future.result()
            events_data = events_future.result()
            datetime_data = datetime_future.result()

        logger.debug("天気予報データ取得完了: %s", weather_data)
        logger.debug("予定データ取得完了: %d件", len(events_data))
        logger.debug("日時情報取得完了: %s", datetime_data)

        # 4. プロンプトを構築
        built_user_prompt = self._build_user_prompt(
            user_prompt, weather_data, events_data, datetime_data
        )

        # 5. OpenAI APIで挨拶を生成
        greeting_text = self.openai_client.generate_text(
            prompt=built_user_prompt,
            system_prompt=system_prompt,
        )
        logger.info("挨拶生成完了: %d文字", len(greeting_text))

        result: dict[str, Any] = {
            "greeting_text": greeting_text,
        }

        # 6. TTS音声合成（オプション指定時）
        if tts_options is not None:
            audio_data = self._synthesize_audio(greeting_text, tts_options)
            result["audio_data"] = audio_data

        return result

    def _synthesize_audio(
        self,
        text: str,
        tts_options: dict[str, Any],
    ) -> bytes:
        """テキストから音声を合成.

        Args:
            text: 合成するテキスト
            tts_options: TTSオプション（モデルから取得した値を使用）

        Returns:
            WAV形式の音声データ
        """
        logger.info("TTS音声合成開始")
        audio_data = self.tts_client.synthesize(
            text=text,
            model=tts_options["model"],
            style=tts_options["style"],
            style_weight=tts_options["style_weight"],
            speed=tts_options["speed"],
            sdp_ratio=tts_options["sdp_ratio"],
            noise_scale=tts_options["noise_scale"],
            noise_scale_w=tts_options["noise_scale_w"],
        )
        logger.info("TTS音声合成完了: %d bytes", len(audio_data))
        return audio_data

    def _get_datetime_info(self) -> dict[str, Any]:
        """日時情報を取得.

        Returns:
            日時情報を含むdict
        """
        now = datetime.now(timezone.get_current_timezone())
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        day_of_week = now.strftime("%A")
        day_of_week_ja = DAY_OF_WEEK_JA.get(day_of_week, day_of_week)

        holiday_name = self.holiday_client.get_holiday_name(date_str)

        return {
            "date": date_str,
            "time": time_str,
            "day_of_week": day_of_week,
            "day_of_week_ja": day_of_week_ja,
            "holiday_name": holiday_name,
        }

    def _build_user_prompt(
        self,
        template: str,
        weather_data: dict[str, Any],
        events_data: list[dict[str, Any]],
        datetime_data: dict[str, Any] | None = None,
    ) -> str:
        """ユーザープロンプトを構築.

        Args:
            template: プロンプトテンプレート
            weather_data: 天気予報データ
            events_data: 予定データ
            datetime_data: 日時情報データ

        Returns:
            ユーザープロンプト文字列

        Note:
            テンプレートマーカー（{{weather}}, {{events}}, {{datetime}}）は
            一括置換されるため、データ内にマーカーが含まれていても安全。
        """
        weather_json = json.dumps(weather_data, ensure_ascii=False, indent=2)
        events_json = json.dumps(events_data, ensure_ascii=False, indent=2)
        datetime_json = json.dumps(datetime_data or {}, ensure_ascii=False, indent=2)

        replacements = {
            "{{weather}}": weather_json,
            "{{events}}": events_json,
            "{{datetime}}": datetime_json,
        }

        # 一括置換（データ内のマーカーは置換対象外）
        pattern = re.compile("|".join(re.escape(k) for k in replacements))
        return pattern.sub(lambda m: replacements[m.group(0)], template)
