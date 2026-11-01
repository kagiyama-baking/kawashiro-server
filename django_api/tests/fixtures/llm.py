"""LLM 呼び出しのテスト用ヘルパ.

`Agent.override(model=ScriptedLLM(...).model)` で実モデルを差し替えて使う。
`FunctionModel` は `ALLOW_MODEL_REQUESTS=False` の対象外で、ネットワークへ出ない。
"""

import json
from dataclasses import dataclass

import httpx2
from openai import AsyncOpenAI
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition

from integrations.llm.config import LLMSettings


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


@dataclass(frozen=True)
class RecordedRequest:
    """モデルが受け取った 1 回分のリクエスト."""

    messages: list[ModelMessage]
    instructions: str | None
    model_settings: ModelSettings | None
    function_tools: list[ToolDefinition]

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


class ScriptedLLM:
    """台本どおりに応答し、受け取った内容を記録する LLM の代役.

    台本の各要素は文字列（テキスト応答）、`ModelResponse`、例外（送出する）のいずれか。
    台本が尽きたリクエストは `IndexError` になる（想定外の追加呼び出しを検出するため）。
    """

    def __init__(self, *script: str | ModelResponse | Exception):
        self._script = list(script)
        self.requests: list[RecordedRequest] = []
        self.model = FunctionModel(self._respond)

    def enqueue(self, *steps: str | ModelResponse | Exception) -> None:
        """台本の末尾に応答を足す."""
        self._script.extend(steps)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.requests.append(
            RecordedRequest(
                messages=list(messages),
                instructions=info.instructions,
                model_settings=info.model_settings,
                function_tools=list(info.function_tools),
            )
        )
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, ModelResponse):
            return step
        return ModelResponse(parts=[TextPart(content=step)])


def litellm_response(
    content: str | None = "OK",
    *,
    finish_reason: str = "stop",
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
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
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
