"""Talk のチャットのサービス（プロンプトの確定・応答・タイトル・音声合成）."""

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from langfuse import observe

from integrations.langfuse.client import langfuse_session, resolve_required_prompt
from integrations.llm.config import get_llm_settings
from integrations.llm.runtime import run_agent_sync, stream_text_sync
from integrations.llm.skills import resolve_skill_body
from integrations.tts.client import TTSClient, TTSResult

from .llm_agents import TALK_CHAT_AGENT, TALK_TITLE_AGENT, split_conversation

if TYPE_CHECKING:
    from integrations.llm.models import AgentSkill

    from .models import TalkSetting

logger = logging.getLogger(__name__)

# チャットのシーン（スキル）の本文の前に置く見出し
SCENE_SECTION_HEADING = "# シーン設定"


class TalkService:
    """Talk のチャットのサービス."""

    def __init__(self):
        """サービスを初期化."""
        self._tts_client = None

    @property
    def tts_client(self) -> TTSClient:
        """TTSクライアントを取得（遅延初期化）."""
        if self._tts_client is None:
            self._tts_client = TTSClient()
        return self._tts_client

    # LLM 応答の最大トークン数。コスト/サイズの上限を強制し、
    # クライアントから無制限に引き出されないようにする。
    CHAT_MAX_OUTPUT_TOKENS = 1024

    def prepare_chat_prompt(
        self, setting: "TalkSetting", skill: "AgentSkill | None" = None
    ) -> str:
        """チャットの system プロンプトを確定する（LLM を呼ぶ前の検証を含む）.

        LLM の設定を先に確かめ（Langfuse に問い合わせる前に止める）、Talk 設定の
        システムプロンプトを参照から解決する。シーン（スキル）があれば、本文を Langfuse
        から取り（フォールバックはない）、「# シーン設定」の節として後ろに足す。変数は
        展開しない。応答のストリームを始める前に呼び、失敗を通常の HTTP ステータスで
        返せるようにする。

        Args:
            setting: チャットの Talk 設定
            skill: チャットのシーン（なしなら None）

        Returns:
            system プロンプト（シーンがあれば、その節を足したもの）

        Raises:
            LLMConfigurationError: LLM 設定がない場合
            PromptUnavailableError: システムプロンプトの本文が空か、シーンの本文を
                取れないか空の場合
        """
        get_llm_settings("talk")
        system_prompt = resolve_required_prompt(setting.system_prompt_ref)
        if skill is None:
            return system_prompt
        return (
            f"{system_prompt}\n\n{SCENE_SECTION_HEADING}\n\n{resolve_skill_body(skill)}"
        )

    @observe(name="talk/chat", capture_input=False)
    def stream_chat_reply(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        *,
        session_id: str | None = None,
    ) -> Iterator[str]:
        """過去の会話を引き継いで応答を生成し、本文の増分を順に返す.

        `messages` はそのまま LLM に渡す（user メッセージ内の変数 `{{datetime}}` などは
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
        with langfuse_session(session_id):
            yield from stream_text_sync(
                TALK_CHAT_AGENT,
                get_llm_settings("talk"),
                user_prompt=user_prompt,
                deps=system_prompt,
                message_history=history,
                max_tokens=self.CHAT_MAX_OUTPUT_TOKENS,
            )

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
        with langfuse_session(session_id):
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
