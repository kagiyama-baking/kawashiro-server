"""アシスタント機能のビジネスロジック."""

import base64
import json
from datetime import date
from typing import Any

import requests

from .openai_client import OpenAIClient
from .prompts import (
    CHAT_SYSTEM_PROMPT,
    DAILY_SUMMARY_PROMPT,
    GREETING_SYSTEM_PROMPT,
    GREETING_USER_PROMPT,
    format_events_for_prompt,
    format_weather_for_prompt,
)
from .tools import ASSISTANT_TOOLS, ToolExecutor

TTS_TIMEOUT = 60


class AssistantService:
    """アシスタント機能のビジネスロジック."""

    def __init__(
        self,
        openai_client: OpenAIClient,
        outlook_client: Any,
        weather_client: Any,
        tts_service_url: str,
    ):
        """初期化.

        Args:
            openai_client: OpenAI APIクライアント
            outlook_client: Outlookカレンダークライアント
            weather_client: 天気予報クライアント
            tts_service_url: TTSサービスのURL
        """
        self.openai = openai_client
        self.outlook = outlook_client
        self.weather = weather_client
        self.tts_url = tts_service_url
        self.tool_executor = ToolExecutor(outlook_client, weather_client)

    def generate_greeting(
        self,
        area_code: str,
        greeting_type: str = "morning",
        include_audio: bool = False,
    ) -> dict[str, Any]:
        """挨拶を生成.

        Args:
            area_code: 天気予報の地域コード
            greeting_type: 挨拶タイプ（morning, afternoon, evening）
            include_audio: 音声を含めるか

        Returns:
            挨拶テキストと関連情報
        """
        # 今日の予定を取得
        today = date.today()
        events = self.outlook.get_calendar_events(today, today)

        # 天気を取得
        weather = self.weather.get_weather(area_code, 0)

        # プロンプトを構築
        system_prompt = GREETING_SYSTEM_PROMPT.format(greeting_type=greeting_type)
        user_prompt = GREETING_USER_PROMPT.format(
            greeting_type=greeting_type,
            events=format_events_for_prompt(events),
            weather=format_weather_for_prompt(weather),
        )

        # テキスト生成
        text = self.openai.generate_text(user_prompt, system_prompt=system_prompt)

        # 天気サマリー作成
        weather_summary = self._create_weather_summary(weather)

        result: dict[str, Any] = {
            "text": text,
            "events_count": len(events),
            "weather_summary": weather_summary,
            "audio": None,
        }

        # 音声生成（オプション）
        if include_audio:
            audio_data = self._synthesize_audio(text)
            if audio_data:
                result["audio"] = base64.b64encode(audio_data).decode("utf-8")

        return result

    def chat(
        self,
        message: str,
        area_code: str | None = None,
        include_audio: bool = False,
    ) -> dict[str, Any]:
        """対話型チャット（Function Calling対応）.

        Args:
            message: ユーザーメッセージ
            area_code: 天気取得用の地域コード（オプション）
            include_audio: 音声を含めるか

        Returns:
            回答テキストと関連情報
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]

        tools_used: list[str] = []
        response = None

        # 最大3回のツール呼び出しループ
        for _ in range(3):
            response = self.openai.chat_completion(messages, tools=ASSISTANT_TOOLS)

            # ツール呼び出しがない場合は終了
            if not response.tool_calls:
                break

            # ツール呼び出しを処理
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
            )

            for tool_call in response.tool_calls:
                tool_name = tool_call.function.name
                tools_used.append(tool_name)

                # ツール実行
                tool_result = self.tool_executor.execute_from_json(
                    tool_name, tool_call.function.arguments
                )

                # ツール結果をメッセージに追加
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

            # ツール結果を元に再度応答を取得
            response = self.openai.chat_completion(messages, tools=ASSISTANT_TOOLS)
            if not response.tool_calls:
                break

        reply = response.content or "" if response else ""

        result: dict[str, Any] = {
            "reply": reply,
            "tools_used": tools_used,
            "audio": None,
        }

        if include_audio and reply:
            audio_data = self._synthesize_audio(reply)
            if audio_data:
                result["audio"] = base64.b64encode(audio_data).decode("utf-8")

        return result

    def generate_daily_summary(
        self,
        area_code: str,
        include_audio: bool = False,
    ) -> dict[str, Any]:
        """日次サマリーを生成.

        Args:
            area_code: 天気予報の地域コード
            include_audio: 音声を含めるか

        Returns:
            サマリーテキストと関連情報
        """
        today = date.today()

        # 今日の予定を取得
        events = self.outlook.get_calendar_events(today, today)

        # 天気を取得
        weather = self.weather.get_weather(area_code, 0)

        # プロンプトを構築
        prompt = DAILY_SUMMARY_PROMPT.format(
            events=format_events_for_prompt(events),
            weather=format_weather_for_prompt(weather),
        )

        # テキスト生成
        summary = self.openai.generate_text(prompt)

        result: dict[str, Any] = {
            "summary": summary,
            "date": today.isoformat(),
            "audio": None,
        }

        if include_audio:
            audio_data = self._synthesize_audio(summary)
            if audio_data:
                result["audio"] = base64.b64encode(audio_data).decode("utf-8")

        return result

    def _synthesize_audio(self, text: str) -> bytes | None:
        """TTSサービスで音声合成.

        Args:
            text: 合成するテキスト

        Returns:
            音声データ（WAV形式）、失敗時はNone
        """
        try:
            response = requests.post(
                f"{self.tts_url}/synthesize",
                json={"text": text},
                timeout=TTS_TIMEOUT,
            )
            if response.status_code == 200:
                return response.content
            return None
        except requests.exceptions.RequestException:
            return None

    def _create_weather_summary(self, weather: dict[str, Any]) -> str:
        """天気サマリーを作成.

        Args:
            weather: 天気情報

        Returns:
            サマリー文字列
        """
        weather_desc = weather.get("weather", "")
        temp_max = weather.get("temp_max")

        if temp_max is not None:
            return f"{weather_desc} 最高気温{temp_max}℃"
        return weather_desc
