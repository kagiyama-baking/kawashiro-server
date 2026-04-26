"""会話生成サービス."""

import json
import logging
from collections.abc import Callable
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from datetime import date, datetime
from functools import partial
from typing import TYPE_CHECKING, Any

from django.utils import timezone
from langfuse import observe

from integrations.langfuse.client import (
    extract_variables,
    get_prompt_with_variables,
    render_template,
)
from integrations.llm.client import LLMClient
from integrations.msgraph import OutlookMSGraphClient
from integrations.tts.client import TTSClient, TTSResult
from integrations.weather.client import WeatherClient

from .constants import DAY_OF_WEEK_JA
from .exceptions import PlaceholderDataMissingError
from .holiday_client import HolidayClient

if TYPE_CHECKING:
    from .models import TalkConfig

logger = logging.getLogger(__name__)

SUPPORTED_PLACEHOLDERS = frozenset({"weather", "events", "datetime"})


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
        user_prompt: str | None = None,
    ) -> dict[str, Any]:
        """会話を生成.

        プロンプト（system + user）に含まれるプレースホルダー `{{weather}}` /
        `{{events}}` / `{{datetime}}` を検出し、必要なデータのみ並列取得する。

        Args:
            config: 会話生成設定
            user_prompt: 任意のユーザープロンプト。指定時は Langfuse の
                user_prompt_ref をスキップし、この文字列に対してプレースホルダー
                展開を行う。

        Returns:
            生成結果を含むdict（greeting_text, audio_data（オプション））

        Raises:
            PlaceholderDataMissingError: プロンプトが要求するデータの取得設定が
                不足している場合（例: {{weather}} 使用時の area_code 未設定）
        """
        logger.info("会話を生成: config=%s", config.name)

        system_compile, user_compile, required_keys = self._prepare_compile_context(
            config, user_prompt
        )
        logger.debug("検出されたプレースホルダー: %s", required_keys)

        self._validate_requirements(config, required_keys)

        data = self._fetch_placeholder_data(config, required_keys)
        variables = self._build_prompt_variables(data)

        greeting_text = self._generate_greeting(
            system_compile(**variables), user_compile(**variables)
        )

        result: dict[str, Any] = {"greeting_text": greeting_text}

        tts_options = config.get_tts_options()
        if tts_options is not None:
            tts_result = self._synthesize_audio(greeting_text, tts_options)
            result["audio_data"] = tts_result.audio_data
            result["audio_content_type"] = tts_result.content_type
            result["audio_format"] = tts_result.format

        return result

    def _prepare_compile_context(
        self,
        config: "TalkConfig",
        user_prompt: str | None,
    ) -> tuple[Callable[..., str], Callable[..., str], set[str]]:
        """system/user プロンプトの compile 関数と必要プレースホルダーを取得."""
        system_compile, system_vars = get_prompt_with_variables(
            config.system_prompt_ref
        )
        if user_prompt is None:
            user_compile, user_vars = get_prompt_with_variables(config.user_prompt_ref)
        else:
            user_vars = extract_variables(user_prompt)
            template = user_prompt

            def user_compile(**kwargs: Any) -> str:
                return render_template(template, kwargs)

        required_keys = (system_vars | user_vars) & SUPPORTED_PLACEHOLDERS
        return system_compile, user_compile, required_keys

    @observe(name="talk/chat")
    def synthesize_chat(
        self,
        config: "TalkConfig",
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        """過去会話履歴を引き継ぐチャット応答を生成する.

        config の system_prompt のみを Langfuse から取得し、プレースホルダー
        `{{weather}}` / `{{events}}` / `{{datetime}}` を検出して必要なデータを
        並列取得して埋め込む。`messages` はそのまま Chat Completions API に
        流す（user メッセージ内のプレースホルダーは展開しない）。

        Args:
            config: 会話生成設定
            messages: 会話履歴 `[{"role": "user"|"assistant", "content": ...}]`。
                末尾は user メッセージである必要がある（バリデーションは
                シリアライザ側で行う）。

        Returns:
            生成結果を含む dict（message, 任意で audio_data /
            audio_content_type / audio_format）

        Raises:
            PlaceholderDataMissingError: system_prompt が要求するデータ取得設定が
                不足している場合（例: {{weather}} 使用時の area_code 未設定）
        """
        logger.info(
            "チャット応答を生成: config=%s, messages=%d件",
            config.name,
            len(messages),
        )

        system_compile, required_keys = self._prepare_chat_context(config)
        logger.debug("検出されたプレースホルダー: %s", required_keys)

        self._validate_requirements(config, required_keys)

        data = self._fetch_placeholder_data(config, required_keys)
        variables = self._build_prompt_variables(data)
        system_prompt = system_compile(**variables)

        assistant_text = self._generate_chat_reply(system_prompt, messages)

        result: dict[str, Any] = {
            "message": {"role": "assistant", "content": assistant_text},
        }

        tts_options = config.get_tts_options()
        if tts_options is not None:
            tts_result = self._synthesize_audio(assistant_text, tts_options)
            result["audio_data"] = tts_result.audio_data
            result["audio_content_type"] = tts_result.content_type
            result["audio_format"] = tts_result.format

        return result

    def _prepare_chat_context(
        self,
        config: "TalkConfig",
    ) -> tuple[Callable[..., str], set[str]]:
        """Chat 用に system プロンプトの compile 関数と必要プレースホルダーを取得."""
        system_compile, system_vars = get_prompt_with_variables(
            config.system_prompt_ref
        )
        required_keys = system_vars & SUPPORTED_PLACEHOLDERS
        return system_compile, required_keys

    # LLM 応答の最大トークン数。コスト/サイズの上限を強制し、
    # クライアントから無制限に引き出されないようにする。
    CHAT_MAX_OUTPUT_TOKENS = 1024

    def _generate_chat_reply(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> str:
        """過去履歴を含めて LLM に問い合わせ、assistant 応答を取得する."""
        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]
        response = self.llm_client.chat_completion(
            full_messages,
            max_tokens=self.CHAT_MAX_OUTPUT_TOKENS,
        )
        assistant_text = response.choices[0].message.content or ""
        logger.info("チャット応答生成完了: %d文字", len(assistant_text))
        return assistant_text

    def _generate_greeting(self, system_prompt: str, user_prompt: str) -> str:
        """LLM でテキスト生成."""
        greeting_text = self.llm_client.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        logger.info("会話生成完了: %d文字", len(greeting_text))
        return greeting_text

    def _validate_requirements(
        self, config: "TalkConfig", required_keys: set[str]
    ) -> None:
        """プレースホルダー要求に対する config 設定の事前検証.

        現状は `{{weather}}` 要求時の `area_code` のみ同期検証する。
        `{{events}}` に対する MS Graph 設定不備や `{{datetime}}` の祝日 API
        到達性は外部 API 呼び出し時のエラー伝播に委ねる（view で 502/503/504）。
        """
        if "weather" in required_keys and not config.area_code:
            raise PlaceholderDataMissingError(
                "プロンプトに {{weather}} が含まれていますが、config.area_code "
                "が未設定です"
            )

    def _fetch_placeholder_data(
        self,
        config: "TalkConfig",
        required_keys: set[str],
    ) -> dict[str, Any]:
        """required_keys に含まれるプレースホルダーデータのみ並列取得する.

        いずれかの future が例外を送出した場合、未完了の future は即キャンセルし、
        最初の例外を呼び出し元へ伝播する。
        """
        tasks = self._build_fetch_tasks(config, required_keys)
        if not tasks:
            return {}

        with ThreadPoolExecutor(max_workers=min(len(tasks), 3)) as executor:
            futures = {key: executor.submit(task) for key, task in tasks.items()}
            _, not_done = wait(futures.values(), return_when=FIRST_EXCEPTION)
            for future in not_done:
                future.cancel()
            data = {}
            for key, future in futures.items():
                data[key] = future.result()
                logger.debug("%sデータ取得完了", key)
        return data

    def _build_fetch_tasks(
        self,
        config: "TalkConfig",
        required_keys: set[str],
    ) -> dict[str, Callable[[], Any]]:
        """required_keys に対応する取得タスク関数を構築."""
        tasks: dict[str, Callable[[], Any]] = {}
        if "weather" in required_keys:
            tasks["weather"] = partial(
                self.weather_client.get_weather, config.area_code, 0
            )
        if "events" in required_keys:
            today = date.today()
            tasks["events"] = partial(
                self.outlook_client.get_calendar_events,
                start_date=today,
                end_date=today,
            )
        if "datetime" in required_keys:
            tasks["datetime"] = self._get_datetime_info
        return tasks

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

    def _build_prompt_variables(self, data: dict[str, Any]) -> dict[str, str]:
        """プレースホルダーデータを LangfusePromptRef 用変数に変換する.

        構造化データ（dict / list）は JSON 文字列化して渡す。
        未使用のプレースホルダーは空文字にしておき、テンプレ側の
        `{{weather}}` `{{events}}` `{{datetime}}` がそのまま残らないようにする。
        """
        variables: dict[str, str] = dict.fromkeys(SUPPORTED_PLACEHOLDERS, "")
        for key in SUPPORTED_PLACEHOLDERS:
            if key in data:
                variables[key] = json.dumps(data[key], ensure_ascii=False, indent=2)
        return variables

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
