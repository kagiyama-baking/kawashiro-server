"""Services for greeting app."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from llm_client.openai_client import OpenAIClient
from msgraph_client import OutlookMSGraphClient
from train.yahoo_client import YahooTransitClient
from tts.client import TTSClient
from weather.jma_client import JMAWeatherClient

logger = logging.getLogger(__name__)


class MorningGreetingService:
    """朝の挨拶生成サービス."""

    def __init__(self):
        """サービスを初期化."""
        self._jma_client = None
        self._outlook_client = None
        self._yahoo_client = None
        self._openai_client = None
        self._tts_client = None

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
    def yahoo_client(self) -> YahooTransitClient:
        """Yahoo!クライアントを取得（遅延初期化）."""
        if self._yahoo_client is None:
            self._yahoo_client = YahooTransitClient()
        return self._yahoo_client

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

    def generate_greeting(
        self,
        area_code: str,
        rail_ids: list[str],
        system_prompt: str,
        user_prompt: str,
        tts_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """朝の挨拶を生成.

        Args:
            area_code: 予報区コード
            rail_ids: 路線IDのリスト
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
        logger.info(
            "朝の挨拶を生成: area_code=%s, rail_ids=%s",
            area_code,
            rail_ids,
        )

        # 外部API呼び出しを並列実行
        today = date.today()

        def fetch_weather():
            return self.jma_client.get_weather(area_code, 0)

        def fetch_events():
            return self.outlook_client.get_calendar_events(
                start_date=today,
                end_date=today,
            )

        def fetch_diainfo():
            return self.yahoo_client.fetch_multiple_diainfo(rail_ids)

        with ThreadPoolExecutor(max_workers=3) as executor:
            weather_future = executor.submit(fetch_weather)
            events_future = executor.submit(fetch_events)
            diainfo_future = executor.submit(fetch_diainfo)

            # 結果を取得（例外があればここで再送出される）
            weather_data = weather_future.result()
            events_data = events_future.result()
            diainfo_data = diainfo_future.result()

        logger.debug("天気予報データ取得完了: %s", weather_data)
        logger.debug("予定データ取得完了: %d件", len(events_data))
        logger.debug("路線運行情報取得完了: %d件", len(diainfo_data))

        # 4. プロンプトを構築
        built_user_prompt = self._build_user_prompt(
            user_prompt, weather_data, events_data, diainfo_data
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

    def _build_user_prompt(
        self,
        template: str,
        weather_data: dict[str, Any],
        events_data: list[dict[str, Any]],
        diainfo_data: list[dict[str, Any]],
    ) -> str:
        """ユーザープロンプトを構築.

        Args:
            template: プロンプトテンプレート
            weather_data: 天気予報データ
            events_data: 予定データ
            diainfo_data: 路線運行情報データ

        Returns:
            ユーザープロンプト文字列

        Note:
            テンプレートマーカー（{{weather}}, {{events}}, {{diainfo}}）は
            一括置換されるため、データ内にマーカーが含まれていても安全。
        """
        import re

        weather_json = json.dumps(weather_data, ensure_ascii=False, indent=2)
        events_json = json.dumps(events_data, ensure_ascii=False, indent=2)
        diainfo_json = json.dumps(diainfo_data, ensure_ascii=False, indent=2)

        replacements = {
            "{{weather}}": weather_json,
            "{{events}}": events_json,
            "{{diainfo}}": diainfo_json,
        }

        # 一括置換（データ内のマーカーは置換対象外）
        pattern = re.compile("|".join(re.escape(k) for k in replacements))
        return pattern.sub(lambda m: replacements[m.group(0)], template)
