"""LLM 呼び出しのテスト用ヘルパ.

`Agent.override(model=ScriptedLLM(...).model)` で実モデルを差し替えて使う。
`FunctionModel` は `ALLOW_MODEL_REQUESTS=False` の対象外で、ネットワークへ出ない。
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx2
from openai import AsyncOpenAI
from pydantic_ai.messages import (
    InstructionPart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaThinkingCalls,
    DeltaThinkingPart,
    FunctionModel,
)
from pydantic_ai.profiles import ModelProfileSpec
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition

from integrations.llm.config import LLMSettings

# LiteLLM のモデル名は DB 上の任意の文字列。名前の形によって PydanticAI が推定する
# プロファイルが変わるので、代表的な形で本文が変わらないことを確かめる。
LITELLM_ALIASES = [
    "gpt-4o-mini",
    "kimi-k2.5",
    "bedrock/moonshotai.kimi-k2.5",
    "moonshotai/kimi-k2.5",
    "anthropic/claude-sonnet-4-5",
    "openai/gpt-5.4",
    "google/gemini-2.5-flash",
    "deepseek/deepseek-reasoner",
    "o1-mini",
]


def make_llm_settings(service_name: str = "talk") -> LLMSettings:
    """テスト用の LLM 接続設定を作る（DB を読まない）."""
    return LLMSettings(
        proxy_base_url="http://litellm.invalid/v1",
        proxy_api_key="sk-test",
        model_alias="test-alias",
        timeout=60,
        service_name=service_name,
        environment="test",
    )


def tool_calls(*names: str) -> ModelResponse:
    """指定した名前のツールを同じステップで呼ぶ応答を作る."""
    return ModelResponse(
        parts=[
            ToolCallPart(tool_name=name, args={}, tool_call_id=f"call_{index}")
            for index, name in enumerate(names)
        ]
    )


def tool_call(tool_name: str, /, **args: Any) -> ModelResponse:
    """1 つのツールを引数付きで呼ぶ応答を作る.

    呼び出しの ID は PydanticAI が呼び出しごとに振る（実際のプロバイダーと同じく一意）。
    """
    return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args)])


def load_capability(capability_id: str) -> ModelResponse:
    """組み込みの `load_capability` ツールで capability（スキル）を読み込む応答を作る."""
    return tool_call("load_capability", id=capability_id)


@dataclass(frozen=True)
class RecordedRequest:
    """モデルが受け取った 1 回分のリクエスト.

    `instructions` は指示をつないだ文字列、`instruction_parts` はその部分ごと
    （OpenAI Chat では部分ごとに別の system メッセージになる）。
    """

    messages: list[ModelMessage]
    instructions: str | None
    model_settings: ModelSettings | None
    function_tools: list[ToolDefinition]
    instruction_parts: list[InstructionPart] = field(default_factory=list)

    @property
    def system_prompts(self) -> list[str]:
        """system として届いた本文を、指示の各部分・会話の途中の system の順で返す.

        会話の途中の system は、読み込んだ capability の指示など。`FunctionModel` の既定の
        プロファイルでは、それらは `<system>` で囲んだ user メッセージになり、ここではなく
        `conversation` に入る（本番と同じ形で受け取るには `ScriptedLLM(profile=...)`）。
        """
        return [
            *(part.content for part in self.instruction_parts),
            *(
                part.content
                for message in self.messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, SystemPromptPart)
            ),
        ]

    @property
    def conversation(self) -> list[tuple[str, str]]:
        """会話を (role, text) の並びで返す（ツール呼び出しなどは含めない）."""
        turns: list[tuple[str, str]] = []
        for message in self.messages:
            if isinstance(message, ModelResponse):
                turns.append(("assistant", message.text or ""))
            elif isinstance(message, ModelRequest):
                turns.extend(
                    ("user", part.content)
                    for part in message.parts
                    if isinstance(part, UserPromptPart)
                )
        return turns

    @property
    def user_prompt(self) -> str:
        """最後のユーザーメッセージを返す."""
        return next(
            text for role, text in reversed(self.conversation) if role == "user"
        )


@dataclass(frozen=True)
class StreamScript:
    """ストリーミング応答の台本.

    Attributes:
        chunks: 順に流す本文。空なら思考だけの応答（本文なし）になる
        gap: チャンクの間の待ち時間（秒）。デバウンスの幅より長いと別の増分になる
        raises: 最後に送出する例外
        hang: 最後のチャンクの後で止まる（停止・切断のテスト用）
    """

    chunks: tuple[str, ...] = ()
    gap: float = 0.0
    raises: Exception | None = None
    hang: bool = False


def stream_of(
    *chunks: str,
    gap: float = 0.0,
    raises: Exception | None = None,
    hang: bool = False,
) -> StreamScript:
    """ストリーミング応答の台本を作る."""
    return StreamScript(chunks=chunks, gap=gap, raises=raises, hang=hang)


class ScriptedLLM:
    """台本どおりに応答し、受け取った内容を記録する LLM の代役.

    台本の各要素は文字列（テキスト応答）、`ModelResponse`、例外（送出する）のいずれか。
    ストリーミングの実行では `StreamScript` で流し方も指定できる。
    台本が尽きたリクエストは `IndexError` になる（想定外の追加呼び出しを検出するため）。

    `profile` を省略すると `FunctionModel` の既定のプロファイルになる。読み込んだ capability の
    指示を本番と同じく system で受け取るには、本番のプロファイル
    （`integrations.llm.runtime._LITELLM_PROFILE`）を渡す。
    """

    def __init__(
        self,
        *script: str | ModelResponse | StreamScript | Exception,
        profile: ModelProfileSpec | None = None,
    ):
        self._script = list(script)
        self.requests: list[RecordedRequest] = []
        self.model = FunctionModel(
            self._respond, stream_function=self._respond_stream, profile=profile
        )

    def enqueue(self, *steps: str | ModelResponse | StreamScript | Exception) -> None:
        """台本の末尾に応答を足す."""
        self._script.extend(steps)

    def _next_step(
        self, messages: list[ModelMessage], info: AgentInfo
    ) -> str | ModelResponse | StreamScript:
        self.requests.append(
            RecordedRequest(
                messages=list(messages),
                instructions=info.instructions,
                model_settings=info.model_settings,
                function_tools=list(info.function_tools),
                instruction_parts=list(
                    info.model_request_parameters.instruction_parts or []
                ),
            )
        )
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = self._next_step(messages, info)
        if isinstance(step, ModelResponse):
            return step
        return ModelResponse(parts=[TextPart(content=step)])

    async def _respond_stream(
        self, messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaThinkingCalls]:
        step = self._next_step(messages, info)
        if isinstance(step, ModelResponse):
            step = StreamScript(chunks=(step.text or "",))
        elif isinstance(step, str):
            step = StreamScript(chunks=(step,))

        if not step.chunks and step.raises is None and not step.hang:
            # FunctionModel は 1 件以上の出力を要求するので、本文なしは思考だけで表す
            yield {0: DeltaThinkingPart(content="考え中")}
        for index, chunk in enumerate(step.chunks):
            if index and step.gap:
                await asyncio.sleep(step.gap)
            yield chunk
        if step.raises is not None:
            raise step.raises
        if step.hang:
            await asyncio.Event().wait()


def slow_model(seconds: float) -> FunctionModel:
    """`seconds` 秒待ってから本文を返すモデル（実行全体の制限時間のテスト用）.

    待つのは `asyncio.sleep` なので、実行の期限が来ればその場で止まる。期限が効かなければ
    遅れて本文を返すので、待ち時間を期限より十分長くしておくと、テストは待ち続けずに
    「例外が出ない」で失敗する。
    """

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(seconds)
        return ModelResponse(parts=[TextPart(content="遅れた応答")])

    return FunctionModel(respond)


class LiteLLMStreamBody(httpx2.AsyncByteStream):
    """LiteLLM の SSE 応答の本文の代役. 閉じられたかどうかを記録する.

    Args:
        *deltas: 順に流す増分。文字列は本文（`delta.content`）、辞書は `delta` そのもの
        finish_reason: 最後のチャンクの終了理由（`None` なら終了チャンクを送らない）
        usage: 終了後に送る usage
        gap: チャンクの間の待ち時間（秒）
        raises: 増分を流し終えた後に送出する例外（転送エラーの再現）
        hang: 増分を流し終えた後で止まる（停止・切断のテスト用）
        raw: `[DONE]` の前に送る生のバイト列
    """

    def __init__(
        self,
        *deltas: str | dict[str, object],
        finish_reason: str | None = "stop",
        usage: dict[str, object] | None = None,
        gap: float = 0.0,
        raises: Exception | None = None,
        hang: bool = False,
        raw: bytes = b"",
    ):
        self._deltas = deltas
        self._finish_reason = finish_reason
        self._usage = usage
        self._gap = gap
        self._raises = raises
        self._hang = hang
        self._raw = raw
        self.closed = False

    @staticmethod
    def _chunk(
        delta: dict[str, object] | None = None,
        *,
        finish_reason: str | None = None,
        usage: dict[str, object] | None = None,
    ) -> bytes:
        choices = (
            []
            if delta is None
            else [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
        )
        body: dict[str, object] = {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "alias",
            "choices": choices,
        }
        if usage is not None:
            body["usage"] = usage
        return f"data: {json.dumps(body, ensure_ascii=False)}\n\n".encode()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, delta in enumerate(self._deltas):
            if index and self._gap:
                await asyncio.sleep(self._gap)
            yield self._chunk({"content": delta} if isinstance(delta, str) else delta)
        if self._raises is not None:
            raise self._raises
        if self._hang:
            await asyncio.Event().wait()
        if self._finish_reason is not None:
            yield self._chunk({}, finish_reason=self._finish_reason)
        if self._usage is not None:
            yield self._chunk(usage=self._usage)
        if self._raw:
            yield self._raw
        yield b"data: [DONE]\n\n"

    async def aclose(self) -> None:
        self.closed = True

    def response(self) -> httpx2.Response:
        """この本文を返す 200 応答を作る."""
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, stream=self
        )


def litellm_stream(
    *deltas: str | dict[str, object], **options: object
) -> httpx2.Response:
    """LiteLLM の Chat Completions のストリーミング応答を作る."""
    return LiteLLMStreamBody(*deltas, **options).response()


def litellm_response(
    content: str | None = "OK",
    *,
    finish_reason: str = "stop",
    usage: dict[str, object] | None = None,
    **message: object,
) -> httpx2.Response:
    """LiteLLM の Chat Completions の 200 応答を作る."""
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": "alias",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": {"role": "assistant", "content": content, **message},
                }
            ],
            "usage": usage
            or {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


class FakeLiteLLM:
    """台本どおりに応答し、受け取った HTTP リクエストを記録する LiteLLM の代役.

    OpenAI SDK の下の HTTP 層だけを差し替えるので、`OpenAIChatModel` の応答の解釈まで通る。
    `FunctionModel` と違い、ここを通るのは `fake_litellm` フィクスチャを使うテストだけ。
    """

    def __init__(self, *script: httpx2.Response | Exception):
        self._script = list(script)
        self.requests: list[httpx2.Request] = []
        self.clients: list[AsyncOpenAI] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """1 リクエストに台本の次の応答を返す（例外なら送出する）."""
        self.requests.append(request)
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def build_client(self, **kwargs: object) -> AsyncOpenAI:
        """HTTP 層を差し替えた AsyncOpenAI を作る."""
        client = AsyncOpenAI(
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self.handle)),
            max_retries=0,
            **kwargs,
        )
        self.clients.append(client)
        return client

    @property
    def bodies(self) -> list[dict]:
        """受け取ったリクエスト本文を返す."""
        return [json.loads(request.content) for request in self.requests]
