"""会話生成サービス."""

import json
import logging
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import date
from functools import partial
from typing import TYPE_CHECKING, Any

from langfuse import observe

from integrations.holiday import HolidayClient, get_datetime_info
from integrations.langfuse.client import (
    extract_variables,
    get_prompt_with_variables,
    render_template,
)
from integrations.llm.config import get_llm_settings
from integrations.llm.runtime import run_agent_sync, stream_text_sync
from integrations.msgraph import OutlookMSGraphClient
from integrations.tts.client import TTSClient, TTSResult
from integrations.weather.client import WeatherClient

from .exceptions import PlaceholderDataMissingError
from .llm_agents import (
    TALK_CHAT_AGENT,
    TALK_SYNTHESIZE_AGENT,
    TALK_TITLE_AGENT,
    split_conversation,
)

if TYPE_CHECKING:
    from .models import TalkConfig

logger = logging.getLogger(__name__)

SUPPORTED_PLACEHOLDERS = frozenset({"weather", "events", "datetime"})


@contextmanager
def _langfuse_session(session_id: str | None) -> Iterator[None]:
    """現在のトレースと配下の観測に Langfuse セッション ID を伝播する.

    Langfuse の Sessions 機能 (https://langfuse.com/docs/observability/features/sessions)
    で同一チャットセッション内のトレースを集約表示するためのもの。SDK 4 系では
    属性の伝播が with 文になったので、本処理をこの中で実行する。失敗しても
    本処理は継続する。
    """
    context = None
    if session_id:
        try:
            from langfuse import propagate_attributes

            context = propagate_attributes(session_id=str(session_id))
            context.__enter__()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Langfuse session_id 設定失敗: %s", exc)
            context = None
    try:
        yield
    finally:
        if context is not None:
            try:
                context.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Langfuse session_id 解除失敗: %s", exc)


class TalkService:
    """会話生成サービス."""

    def __init__(self):
        """サービスを初期化."""
        self._tts_client = None
        self._holiday_client = None
        self._weather_client = None
        self._outlook_client = None

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
            tts_result = self.synthesize_audio(greeting_text, tts_options)
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

    # LLM 応答の最大トークン数。コスト/サイズの上限を強制し、
    # クライアントから無制限に引き出されないようにする。
    CHAT_MAX_OUTPUT_TOKENS = 1024

    @observe(name="talk/prepare_chat", capture_input=False, capture_output=False)
    def prepare_chat_prompt(self, config: "TalkConfig") -> str:
        """チャットの system プロンプトを確定する（LLM を呼ぶ前の検証を含む）.

        config の system_prompt のみを Langfuse から取得し、プレースホルダー
        `{{weather}}` / `{{events}}` / `{{datetime}}` を検出して必要なデータを
        並列取得して埋め込む。応答のストリームを始める前に呼び、失敗を通常の HTTP
        ステータスで返せるようにする。

        Args:
            config: 会話生成設定

        Returns:
            展開済みの system プロンプト

        Raises:
            PlaceholderDataMissingError: system_prompt が要求するデータ取得設定が
                不足している場合（例: {{weather}} 使用時の area_code 未設定）
            LLMConfigurationError: LLM 設定がない場合
        """
        system_compile, required_keys = self._prepare_chat_context(config)
        logger.debug("検出されたプレースホルダー: %s", required_keys)

        self._validate_requirements(config, required_keys)

        data = self._fetch_placeholder_data(config, required_keys)
        system_prompt = system_compile(**self._build_prompt_variables(data))

        get_llm_settings("talk")
        return system_prompt

    @observe(name="talk/chat", capture_input=False)
    def stream_chat_reply(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        *,
        session_id: str | None = None,
    ) -> Iterator[str]:
        """過去の会話を引き継いで応答を生成し、本文の増分を順に返す.

        `messages` はそのまま LLM に渡す（user メッセージ内のプレースホルダーは
        展開しない）。本文のない応答は増分なしで正常に終わる。`close()` で閉じると
        LLM への接続もその場で閉じる。

        Args:
            system_prompt: `prepare_chat_prompt` で確定した system プロンプト
            messages: 会話履歴 `[{"role": "user"|"assistant", "content": ...}]`。
                末尾は user メッセージ
            session_id: Langfuse のセッション ID（チャットセッションの UUID）

        Yields:
            本文の増分

        Raises:
            LLMConfigurationError: LLM 設定がない場合
            LLMClientError: LLM の実行に失敗した場合（`LLMTimeoutError` などを含む）
        """
        logger.info("チャット応答を生成: messages=%d件", len(messages))
        history, user_prompt = split_conversation(messages)
        with _langfuse_session(session_id):
            yield from stream_text_sync(
                TALK_CHAT_AGENT,
                get_llm_settings("talk"),
                user_prompt=user_prompt,
                deps=system_prompt,
                message_history=history,
                max_tokens=self.CHAT_MAX_OUTPUT_TOKENS,
            )

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

    # セッションタイトル要約用の出力上限。20 文字程度に収める想定だが
    # 余裕を持って 60 トークン。
    SESSION_TITLE_MAX_OUTPUT_TOKENS = 60
    SESSION_TITLE_MAX_LENGTH = 50

    @observe(name="talk/generate_session_title")
    def generate_session_title(
        self,
        messages: list[dict[str, str]],
        *,
        session_id: str | None = None,
    ) -> str:
        """会話履歴から短いセッションタイトルを LLM で要約生成する.

        失敗時は空文字を返す（呼び出し側で title 設定をスキップ）。
        """
        with _langfuse_session(session_id):
            return self._generate_session_title(messages)

    def _generate_session_title(self, messages: list[dict[str, str]]) -> str:
        """セッションタイトル生成の本体（Langfuse の属性の伝播の中で実行する）."""
        if not messages:
            return ""

        system_prompt = (
            "以下の会話の内容を表す短いタイトルを、日本語で 1 行・"
            "20 文字以内で 1 つだけ出力してください。"
            "出力はタイトル本文のみとし、引用符・記号・前置きは含めないでください。"
        )
        # 履歴が長い場合でもトークンを節約するため先頭 4 件まで利用
        sample = messages[:4]
        joined = "\n".join(f"{m['role']}: {m['content']}" for m in sample)

        try:
            result = run_agent_sync(
                TALK_TITLE_AGENT,
                get_llm_settings("talk"),
                user_prompt=joined,
                instructions=system_prompt,
                max_tokens=self.SESSION_TITLE_MAX_OUTPUT_TOKENS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("セッションタイトル生成失敗: %s", exc)
            return ""

        title = (result.output or "").strip()
        # 改行・引用符などを軽く正規化、長すぎる場合は丸める
        title = title.splitlines()[0] if title else ""
        title = title.strip("「」\"' 　")
        if len(title) > self.SESSION_TITLE_MAX_LENGTH:
            title = title[: self.SESSION_TITLE_MAX_LENGTH]
        return title

    def _generate_greeting(self, system_prompt: str, user_prompt: str) -> str:
        """LLM でテキスト生成."""
        result = run_agent_sync(
            TALK_SYNTHESIZE_AGENT,
            get_llm_settings("talk"),
            user_prompt=user_prompt,
            instructions=system_prompt,
        )
        greeting_text = result.output or ""
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
            tasks["datetime"] = partial(get_datetime_info, self.holiday_client)
        return tasks

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

    def synthesize_audio(
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
