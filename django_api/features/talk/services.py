"""会話生成サービス."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone
from langfuse import observe

from integrations.llm.client import LLMClient
from integrations.msgraph import OutlookMSGraphClient
from integrations.tts.client import TTSClient, TTSResult
from integrations.weather.client import WeatherClient

from .constants import DAY_OF_WEEK_JA
from .holiday_client import HolidayClient

if TYPE_CHECKING:
    from .models import TalkConfig

logger = logging.getLogger(__name__)


class TalkService:
    """会話生成サービス."""

    def __init__(self):
        """サービスを初期化."""
        self._llm_client = None
        self._tts_client = None
        self._holiday_client = None
        self._weather_client = None
        self._outlook_client = None

    @property
    def llm_client(self) -> LLMClient:
        """LLMクライアントを取得（遅延初期化）."""
        if self._llm_client is None:
            self._llm_client = LLMClient(service_name="talk")
        return self._llm_client

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
    def weather_client(self) -> WeatherClient:
        """天気予報クライアントを取得（遅延初期化）."""
        if self._weather_client is None:
            self._weather_client = WeatherClient()
        return self._weather_client

    @property
    def outlook_client(self) -> OutlookMSGraphClient:
        """Outlookクライアントを取得（遅延初期化）."""
        if self._outlook_client is None:
            self._outlook_client = OutlookMSGraphClient()
        return self._outlook_client

    @observe(name="talk/synthesize")
    def synthesize(
        self,
        config: "TalkConfig",
        user_prompt: str,
    ) -> dict[str, Any]:
        """会話を生成.

        Args:
            config: 会話生成設定
            user_prompt: ユーザープロンプトテンプレート

        Returns:
            生成結果を含むdict（greeting_text, audio_data（オプション））
        """
        logger.info("会話を生成: config=%s", config.name)

        # 有効なプレースホルダーに応じてデータを取得
        data = self._fetch_placeholder_data(config)

        # プロンプトを構築
        built_user_prompt = self._build_user_prompt(user_prompt, data)

        # OpenAI APIで会話を生成
        greeting_text = self.llm_client.generate_text(
            prompt=built_user_prompt,
            system_prompt=config.system_prompt,
        )
        logger.info("会話生成完了: %d文字", len(greeting_text))

        result: dict[str, Any] = {
            "greeting_text": greeting_text,
        }

        # TTS音声合成（オプション）
        tts_options = config.get_tts_options()
        if tts_options is not None:
            tts_result = self._synthesize_audio(greeting_text, tts_options)
            result["audio_data"] = tts_result.audio_data
            result["audio_content_type"] = tts_result.content_type
            result["audio_format"] = tts_result.format

        return result

    def _fetch_placeholder_data(self, config: "TalkConfig") -> dict[str, Any]:
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
                    self.weather_client.get_weather,
                    config.area_code,
                    0,
                )
            if config.use_events:
                futures["events"] = executor.submit(
                    self.outlook_client.get_calendar_events,
                    start_date=today,
                    end_date=today,
                )
            if config.use_datetime:
                futures["datetime"] = executor.submit(
                    self._get_datetime_info,
                )

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
    ) -> TTSResult:
        """テキストから音声を合成."""
        logger.info("TTS音声合成開始")
        tts_result = self.tts_client.synthesize(
            text=text,
            model=tts_options["model"],
            style=tts_options["style"],
            style_weight=tts_options["style_weight"],
            speed=tts_options["speed"],
            sdp_ratio=tts_options["sdp_ratio"],
            noise_scale=tts_options["noise_scale"],
            noise_scale_w=tts_options["noise_scale_w"],
            format=tts_options.get("format", "wav"),
        )
        logger.info(
            "TTS音声合成完了: %d bytes, format=%s",
            len(tts_result.audio_data),
            tts_result.format,
        )
        return tts_result
