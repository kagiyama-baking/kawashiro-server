"""Services for greeting app."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from llm_client.openai_client import OpenAIClient
from msgraph_client import OutlookMSGraphClient
from tts.client import TTSClient
from weather.jma_client import JMAWeatherClient

from .holiday_client import HolidayClient

if TYPE_CHECKING:
    from .models import GreetingConfig

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


class GreetingService:
    """挨拶生成サービス."""

    def __init__(self):
        """サービスを初期化."""
        self._openai_client = None
        self._tts_client = None
        self._holiday_client = None
        self._jma_client = None
        self._outlook_client = None

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

    def generate_greeting(
        self,
        config: "GreetingConfig",
        user_prompt: str,
    ) -> dict[str, Any]:
        """挨拶を生成.

        Args:
            config: 挨拶設定
            user_prompt: ユーザープロンプトテンプレート

        Returns:
            生成結果を含むdict（greeting_text, audio_data（オプション））
        """
        logger.info("挨拶を生成: config=%s", config.name)

        # 有効なプレースホルダーに応じてデータを取得
        data = self._fetch_placeholder_data(config)

        # プロンプトを構築
        built_user_prompt = self._build_user_prompt(user_prompt, data)

        # OpenAI APIで挨拶を生成
        greeting_text = self.openai_client.generate_text(
            prompt=built_user_prompt,
            system_prompt=config.system_prompt,
        )
        logger.info("挨拶生成完了: %d文字", len(greeting_text))

        result: dict[str, Any] = {
            "greeting_text": greeting_text,
        }

        # TTS音声合成（オプション）
        tts_options = config.get_tts_options()
        if tts_options is not None:
            audio_data = self._synthesize_audio(greeting_text, tts_options)
            result["audio_data"] = audio_data

        return result

    def _fetch_placeholder_data(self, config: "GreetingConfig") -> dict[str, Any]:
        """プレースホルダーに必要なデータを取得.

        有効なプレースホルダーに応じて並列でデータを取得する。
        """
        data: dict[str, Any] = {}
        futures: dict[str, Any] = {}

        # 並列実行するタスク数を計算
        task_count = sum([config.use_weather, config.use_events, config.use_datetime])

        if task_count == 0:
            return data

        today = date.today()

        with ThreadPoolExecutor(max_workers=min(task_count, 3)) as executor:
            if config.use_weather:
                futures["weather"] = executor.submit(
                    self.jma_client.get_weather, config.area_code, 0
                )
            if config.use_events:
                futures["events"] = executor.submit(
                    self.outlook_client.get_calendar_events,
                    start_date=today,
                    end_date=today,
                )
            if config.use_datetime:
                futures["datetime"] = executor.submit(self._get_datetime_info)

            # 結果を取得（例外があればここで再送出される）
            for key, future in futures.items():
                data[key] = future.result()
                logger.debug("%sデータ取得完了: %s", key, data[key])

        return data

    def _get_datetime_info(self) -> dict[str, Any]:
        """日時情報を取得."""
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
        data: dict[str, Any],
    ) -> str:
        """ユーザープロンプトを構築.

        Args:
            template: プロンプトテンプレート
            data: プレースホルダーデータ（weather, events, datetime）

        Returns:
            ユーザープロンプト文字列
        """
        replacements: dict[str, str] = {}

        if "weather" in data:
            replacements["{{weather}}"] = json.dumps(
                data["weather"], ensure_ascii=False, indent=2
            )
        if "events" in data:
            replacements["{{events}}"] = json.dumps(
                data["events"], ensure_ascii=False, indent=2
            )
        if "datetime" in data:
            replacements["{{datetime}}"] = json.dumps(
                data["datetime"], ensure_ascii=False, indent=2
            )

        if not replacements:
            return template

        # 一括置換（データ内のマーカーは置換対象外）
        pattern = re.compile("|".join(re.escape(k) for k in replacements))
        return pattern.sub(lambda m: replacements[m.group(0)], template)

    def _synthesize_audio(
        self,
        text: str,
        tts_options: dict[str, Any],
    ) -> bytes:
        """テキストから音声を合成."""
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
