"""integrations.llm.runtime のテスト.

HTTP 本文の契約は `httpx2.MockTransport` で OpenAI SDK の下まで通して確認する。
実ネットワークへは出ないので、この範囲だけ ALLOW_MODEL_REQUESTS を許可する。
"""

import json
import threading
from dataclasses import replace
from unittest.mock import patch

import httpx2
import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from pydantic import BaseModel
from pydantic_ai import Agent, InstrumentationSettings, PromptedOutput, RunContext
from pydantic_ai.exceptions import (
    ContentFilterError,
    ModelAPIError,
    ModelConnectionError,
    ModelHTTPError,
    ModelRequestTimeout,
    ModelTimeoutError,
    RunCancelled,
    RunTimedOut,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UserError,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from integrations.llm.config import LLMSettings
from integrations.llm.exceptions import (
    LLMClientError,
    LLMOutputError,
    LLMTimeoutError,
)
from integrations.llm.runtime import (
    arun_agent,
    open_model,
    run_agent_sync,
    stream_text_sync,
    translate_llm_errors,
)
from tests.fixtures.llm import LiteLLMStreamBody, litellm_response, litellm_stream

BASE_URL = "http://litellm.invalid/v1"

# LiteLLM のモデル名は DB 上の任意の文字列。名前の形によって PydanticAI が推定する
# プロファイルが変わるので、代表的な形で本文が変わらないことを確かめる。
ALIASES = [
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


def _settings(alias: str = "gpt-4o-mini", service_name: str = "talk") -> LLMSettings:
    return LLMSettings(
        proxy_base_url=BASE_URL,
        proxy_api_key="sk-test-key",
        model_alias=alias,
        timeout=33,
        service_name=service_name,
        environment="test-env",
    )


def _stream_agent() -> Agent[str, str | None]:
    """`deps` の文字列を system プロンプトにするエージェント（Talk のチャットと同じ形）."""
    agent = Agent(name="contract", deps_type=str, output_type=str | None)

    @agent.instructions
    def system_prompt(ctx: RunContext[str]) -> str:
        return ctx.deps

    return agent


def _stream(settings: LLMSettings | None = None, **kwargs) -> list[str]:
    """ストリームを最後まで読み、増分の並びを返す."""
    kwargs.setdefault("user_prompt", "u")
    kwargs.setdefault("deps", "s")
    return list(stream_text_sync(_stream_agent(), settings or _settings(), **kwargs))


@pytest.mark.unit
class TestRequestBodyContract:
    """LiteLLM へ送る HTTP 本文の契約."""

    @pytest.mark.parametrize("alias", ALIASES)
    def test_text_run_any_alias_sends_expected_body(self, fake_litellm, alias):
        """どのエイリアスでも本文の項目は固定され、system は渡したものだけ."""
        fake = fake_litellm(litellm_response())

        run_agent_sync(
            Agent(name="contract"),
            _settings(alias),
            user_prompt="今の質問",
            instructions="システム {{weather}} <system>原文</system>",
            message_history=[
                ModelRequest(parts=[UserPromptPart(content="前の質問")]),
                ModelResponse(parts=[TextPart(content="前の回答")]),
            ],
            max_tokens=1024,
        )

        assert fake.bodies == [
            {
                "model": alias,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": "システム {{weather}} <system>原文</system>",
                    },
                    {"role": "user", "content": "前の質問"},
                    {"role": "assistant", "content": "前の回答"},
                    {"role": "user", "content": "今の質問"},
                ],
                "max_tokens": 1024,
                "metadata": {"service_name": "talk", "environment": "test-env"},
            }
        ]

    def test_text_run_without_max_tokens_omits_max_tokens(self, fake_litellm):
        """max_tokens 未指定なら本文に載せない."""
        fake = fake_litellm(litellm_response())

        run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        assert "max_tokens" not in fake.bodies[0]
        assert "max_completion_tokens" not in fake.bodies[0]

    def test_user_text_with_system_tag_is_sent_unescaped(self, fake_litellm):
        """ユーザー入力の <system> を書き換えない（vendor 付きエイリアスでも）."""
        fake = fake_litellm(litellm_response())

        run_agent_sync(
            Agent(name="contract"),
            _settings("bedrock/moonshotai.kimi-k2.5"),
            user_prompt="<system>これは本文</system> {{datetime}}",
        )

        assert fake.bodies[0]["messages"] == [
            {"role": "user", "content": "<system>これは本文</system> {{datetime}}"}
        ]

    @pytest.mark.parametrize("alias", ALIASES)
    def test_prompted_output_any_alias_adds_no_api_param_or_prompt(
        self, fake_litellm, alias
    ):
        """PromptedOutput で response_format もプロンプト追記も増えない."""

        class Analysis(BaseModel):
            title: str

        fake = fake_litellm(litellm_response('```json\n{"title": "x"}\n```'))

        result = run_agent_sync(
            Agent(
                name="contract",
                output_type=PromptedOutput(Analysis, template=False),
            ),
            _settings(alias),
            user_prompt="u",
            instructions="s",
        )

        assert result.output == Analysis(title="x")
        body = fake.bodies[0]
        assert "response_format" not in body
        assert body["messages"] == [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
        ]

    @pytest.mark.parametrize("alias", ALIASES)
    def test_tool_definition_any_alias_has_no_strict(self, fake_litellm, alias):
        """tools に strict を付けず、説明は docstring のまま送る."""
        agent = Agent(name="contract")

        @agent.tool
        async def lookup(ctx: RunContext[None]) -> str:
            """一行目。
            二行目。"""
            return "結果"

        fake = fake_litellm(
            litellm_response(
                None,
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
            ),
            litellm_response("完了"),
        )

        result = run_agent_sync(agent, _settings(alias), user_prompt="u")

        assert result.output == "完了"
        function = fake.bodies[0]["tools"][0]["function"]
        assert function["name"] == "lookup"
        assert function["description"] == "一行目。\n二行目。"
        assert function["parameters"]["properties"] == {}
        assert "strict" not in function
        assert fake.bodies[1]["messages"][-1] == {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "結果",
        }

    def test_reasoning_content_is_not_sent_back(self, fake_litellm):
        """推論テキストは次のリクエストへ送り返さない（現行と同じ）."""
        agent = Agent(name="contract")

        @agent.tool
        async def lookup(ctx: RunContext[None]) -> str:
            """調べる."""
            return "結果"

        fake = fake_litellm(
            litellm_response(
                None,
                reasoning_content="考え中",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
            ),
            litellm_response("完了"),
        )

        run_agent_sync(agent, _settings(), user_prompt="u")

        assistant = fake.bodies[1]["messages"][-2]
        assert assistant["role"] == "assistant"
        assert "reasoning_content" not in assistant
        assert "考え中" not in json.dumps(fake.bodies[1], ensure_ascii=False)

    def test_request_uses_proxy_url_key_and_timeout(self, fake_litellm):
        """接続先・キー・タイムアウトは LLMSettings の値を使う."""
        fake = fake_litellm(litellm_response())

        run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        request = fake.requests[0]
        assert str(request.url) == f"{BASE_URL}/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-test-key"
        assert request.extensions["timeout"]["read"] == 33


@pytest.mark.unit
class TestOpenModel:
    """open_model のテスト."""

    def test_client_is_closed_after_run(self, fake_litellm):
        """接続はループに属するので実行ごとに閉じる."""
        fake = fake_litellm(litellm_response(), litellm_response())
        agent = Agent(name="contract")

        run_agent_sync(agent, _settings(), user_prompt="1")
        run_agent_sync(agent, _settings(), user_prompt="2")

        assert len(fake.clients) == 2
        assert all(client.is_closed() for client in fake.clients)

    def test_client_is_closed_when_run_fails(self, fake_litellm):
        """失敗時も閉じる."""
        fake = fake_litellm(httpx2.Response(500, json={"error": "boom"}))

        with pytest.raises(LLMClientError):
            run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        assert fake.clients[0].is_closed()

    def test_empty_api_key_still_reaches_litellm(self, fake_litellm):
        """キー未設定でも例外にせず送信し、認証の判断は LiteLLM に任せる.

        openai 3 系は空文字のキーをクライアント生成時に拒否するので、従来の
        「未設定のまま LiteLLM へ送る」動作を保つにはプレースホルダーが要る。
        """
        fake = fake_litellm(litellm_response())
        settings = replace(_settings(), proxy_api_key="")

        run_agent_sync(Agent(name="contract"), settings, user_prompt="u")

        assert len(fake.requests) == 1

    def test_open_model_uses_alias_as_model_name(self, fake_litellm):
        """モデル名はエイリアスをそのまま使う."""
        fake_litellm()

        async def model_name() -> str:
            async with open_model(_settings("custom/alias")) as model:
                return model.model_name

        assert async_to_sync(model_name)() == "custom/alias"


@pytest.mark.unit
class TestTranslateLLMErrors:
    """translate_llm_errors の例外写像."""

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (ModelTimeoutError("m", "timeout"), LLMTimeoutError),
            (ModelRequestTimeout("m", 1.0), LLMTimeoutError),
            (RunTimedOut("timeout"), LLMTimeoutError),
            (UnexpectedModelBehavior("bad output"), LLMOutputError),
            (ContentFilterError("filtered"), LLMOutputError),
            (ModelConnectionError("m", "down"), LLMClientError),
            (ModelHTTPError(429, "m"), LLMClientError),
            (ModelAPIError("m", "bad gateway"), LLMClientError),
            (UsageLimitExceeded("limit"), LLMClientError),
        ],
    )
    def test_agent_error_is_translated(self, error, expected):
        """AgentRunError 系はプロジェクトの例外に変換し、原因を残す."""
        with pytest.raises(LLMClientError) as exc_info, translate_llm_errors():
            raise error

        assert type(exc_info.value) is expected
        assert exc_info.value.__cause__ is error

    def test_output_error_message_excludes_response_body(self):
        """応答本文（推論テキストを含み得る）を例外メッセージ経由でログへ残さない."""
        body = json.dumps({"parts": [{"content": "reasoning-text"}]})

        with pytest.raises(LLMOutputError) as exc_info, translate_llm_errors():
            raise ContentFilterError("filtered", body=body)

        assert "filtered" in str(exc_info.value)
        assert "reasoning-text" not in str(exc_info.value)

    @pytest.mark.parametrize(
        "error", [RunCancelled("stop"), UserError("misuse"), ValueError("other")]
    )
    def test_other_error_is_not_translated(self, error):
        """キャンセルと実装ミスは変換しない."""
        with pytest.raises(type(error)) as exc_info, translate_llm_errors():
            raise error

        assert exc_info.value is error


@pytest.mark.unit
class TestResponseContract:
    """LiteLLM の応答の解釈の契約（FunctionModel では通らない層）."""

    @pytest.mark.parametrize("alias", ALIASES)
    @pytest.mark.parametrize(
        "content",
        [
            "  本文\n\n続き \n",
            "before<think>x</think>after",
            "wrap with <think> and </think> tags",
            "<thinking>考え</thinking>本文",
            '{"title_ja": "uses <think> tag", "summary": "and </think> closes"}',
        ],
    )
    def test_response_text_any_alias_is_returned_verbatim(
        self, fake_litellm, alias, content
    ):
        """本文は空白も思考タグの文字列もそのまま返す（どのエイリアスでも）."""
        fake_litellm(litellm_response(content))

        result = run_agent_sync(
            Agent(name="contract"), _settings(alias), user_prompt="u"
        )

        assert result.output == content

    def test_reasoning_content_is_not_mixed_into_output(self, fake_litellm):
        """推論テキストは出力に混ぜない."""
        fake_litellm(litellm_response("本文", reasoning_content="考え中"))

        result = run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        assert result.output == "本文"

    def test_partial_text_cut_by_token_limit_is_returned(self, fake_litellm):
        """出力上限で途中まででも本文があれば返す."""
        fake_litellm(litellm_response("途中まで", finish_reason="length"))

        result = run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        assert result.output == "途中まで"

    @pytest.mark.parametrize(
        ("content", "finish_reason", "message"),
        [
            (None, "stop", {}),
            ("", "stop", {}),
            (None, "length", {}),
            ("", "length", {}),
            (None, "length", {"reasoning_content": "考えるだけで上限に達した"}),
            (None, "content_filter", {}),
            (None, "stop", {"refusal": "お答えできません"}),
        ],
    )
    def test_response_without_text_with_optional_output_returns_none_without_retry(
        self, fake_litellm, content, finish_reason, message
    ):
        """本文がなければ理由によらず None を返し、再試行しない（従来の `content or ""`）."""
        fake = fake_litellm(
            litellm_response(content, finish_reason=finish_reason, **message)
        )

        result = run_agent_sync(
            Agent(name="contract", output_type=str | None),
            _settings(),
            user_prompt="u",
        )

        assert result.output is None
        assert len(fake.requests) == 1

    def test_non_json_response_raises_llm_client_error(self, fake_litellm):
        """JSON でない 200 応答は LLMClientError 系になる."""
        fake_litellm(
            httpx2.Response(200, text="<html>", headers={"content-type": "text/html"})
        )

        with pytest.raises(LLMClientError):
            run_agent_sync(
                Agent(name="contract", output_type=str | None),
                _settings(),
                user_prompt="u",
            )


@pytest.mark.unit
class TestErrorsThroughHTTP:
    """HTTP 層の失敗が SDK・PydanticAI を通ってプロジェクトの例外になる."""

    @pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 502, 503])
    def test_status_error_raises_llm_client_error(self, fake_litellm, status):
        """従来未捕捉だった APIStatusError 系も LLMClientError になる."""
        fake_litellm(httpx2.Response(status, json={"error": {"message": "x"}}))

        with pytest.raises(LLMClientError) as exc_info:
            run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        assert type(exc_info.value) is LLMClientError

    def test_read_timeout_raises_llm_timeout_error(self, fake_litellm):
        """タイムアウトは LLMTimeoutError になる."""
        fake_litellm(httpx2.ReadTimeout("slow"))

        with pytest.raises(LLMTimeoutError):
            run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

    def test_connect_error_raises_llm_client_error(self, fake_litellm):
        """接続失敗は LLMClientError になる."""
        fake_litellm(httpx2.ConnectError("refused"))

        with pytest.raises(LLMClientError) as exc_info:
            run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        assert type(exc_info.value) is LLMClientError

    def test_undecodable_body_raises_llm_client_error(self, fake_litellm):
        """JSON でない 200 応答も LLMClientError 系になる."""
        fake_litellm(
            httpx2.Response(
                200,
                content=b"not json",
                headers={"content-type": "application/json"},
            )
        )

        with pytest.raises(LLMClientError):
            run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

    def test_empty_text_with_str_output_raises_llm_output_error(self, fake_litellm):
        """str 出力で空応答が続くと LLMOutputError になる."""
        fake_litellm(litellm_response(None), litellm_response(None))

        with pytest.raises(LLMOutputError):
            run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

    def test_empty_text_with_optional_output_returns_none(self, fake_litellm):
        """output_type に None を許すと空応答は再試行せず None を返す."""
        fake = fake_litellm(litellm_response(None))

        result = run_agent_sync(
            Agent(name="contract", output_type=str | None),
            _settings(),
            user_prompt="u",
        )

        assert result.output is None
        assert len(fake.requests) == 1


@pytest.mark.unit
class TestArunAgent:
    """arun_agent の引数の受け渡し."""

    def test_conversation_id_defaults_to_service_name(self, fake_litellm):
        """会話 ID の既定はサービス名で、実行ごとに変わらない.

        Langfuse は会話 ID をセッションとして扱うので、ランダムな既定値のままだと
        実行のたびにセッションが増える。
        """
        fake_litellm(litellm_response("a"), litellm_response("b"))
        agent = Agent(name="contract")

        first = run_agent_sync(agent, _settings(), user_prompt="1")
        second = run_agent_sync(agent, _settings(), user_prompt="2")

        expected = _settings().service_name
        assert first.conversation_id == expected
        assert second.conversation_id == expected

    def test_conversation_id_can_be_specified(self, fake_litellm):
        """会話 ID を指定すると、その値で実行する."""
        fake_litellm(litellm_response("a"))

        result = run_agent_sync(
            Agent(name="contract"),
            _settings(),
            user_prompt="u",
            conversation_id="hn-thread/1",
        )

        assert result.conversation_id == "hn-thread/1"

    def test_usage_breakdown_is_dropped(self, fake_litellm):
        """usage に output の内数を持たない.

        Langfuse は usage の全項目を足して total にするので、残すと output を二重に数える。
        """
        fake_litellm(
            litellm_response(
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                    "completion_tokens_details": {
                        "text_tokens": 2,
                        "reasoning_tokens": 1,
                    },
                }
            )
        )

        result = run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        usage = result.response.usage
        assert (usage.input_tokens, usage.output_tokens) == (10, 3)
        assert usage.details == {}

    def test_usage_limits_are_applied(self, fake_litellm):
        """usage_limits の超過は LLMClientError になる."""
        fake_litellm()

        with pytest.raises(LLMClientError) as exc_info:
            run_agent_sync(
                Agent(name="contract"),
                _settings(),
                user_prompt="u",
                usage_limits=UsageLimits(request_limit=0),
            )

        assert isinstance(exc_info.value.__cause__, UsageLimitExceeded)

    def test_retries_are_applied(self, fake_litellm):
        """retries で出力リトライの回数を指定できる."""

        class Analysis(BaseModel):
            title: str

        fake = fake_litellm(
            litellm_response("x"), litellm_response("y"), litellm_response("z")
        )

        with pytest.raises(LLMOutputError):
            run_agent_sync(
                Agent(
                    name="contract",
                    output_type=PromptedOutput(Analysis, template=False),
                ),
                _settings(),
                user_prompt="u",
                retries={"output": 2},
            )

        assert len(fake.requests) == 3

    def test_deps_are_passed_to_tools(self):
        """deps はツールの RunContext に渡る."""
        agent = Agent(name="contract", deps_type=dict)
        seen = {}

        @agent.tool
        async def remember(ctx: RunContext[dict]) -> str:
            """記録する."""
            seen.update(ctx.deps)
            return "ok"

        with agent.override(model=TestModel()):
            run_agent_sync(agent, _settings(), user_prompt="u", deps={"thread": "t-1"})

        assert seen == {"thread": "t-1"}

    def test_coroutine_can_be_awaited_directly(self):
        """非同期の呼び出し元からは arun_agent を await できる."""
        agent = Agent(name="contract")

        async def call() -> str:
            result = await arun_agent(agent, _settings(), user_prompt="u")
            return result.output

        with agent.override(model=TestModel(custom_output_text="非同期")):
            assert async_to_sync(call)() == "非同期"


@pytest.mark.unit
class TestRunAgentSync:
    """run_agent_sync の同期ブリッジ."""

    def test_sync_to_async_in_tool_runs_on_calling_thread(self):
        """ツール内の sync_to_async は呼び出し元スレッドに戻る."""
        agent = Agent(name="contract")
        seen: dict[str, int] = {}

        def record_thread() -> None:
            seen["prepare"] = threading.get_ident()

        @agent.tool
        async def prepare(ctx: RunContext[None]) -> str:
            """準備する."""
            seen["tool"] = threading.get_ident()
            await sync_to_async(record_thread)()
            return "ok"

        with agent.override(model=TestModel()):
            run_agent_sync(agent, _settings(), user_prompt="u")

        assert seen["prepare"] == threading.get_ident()
        assert seen["tool"] != threading.get_ident()

    def test_repeated_calls_each_use_a_new_loop(self):
        """同じエージェントを続けて実行できる（ループをまたいで資源を持ち越さない）."""
        agent = Agent(name="contract")

        with agent.override(model=TestModel(custom_output_text="ok")):
            outputs = [
                run_agent_sync(agent, _settings(), user_prompt=str(i)).output
                for i in range(3)
            ]

        assert outputs == ["ok", "ok", "ok"]

    def test_error_in_run_propagates_translated(self):
        """実行中の失敗は変換されて呼び出し元に届く."""
        agent = Agent(name="contract")

        @agent.tool_plain
        def always_fail() -> str:
            """失敗する."""
            raise UnexpectedModelBehavior("broken")

        with (
            agent.override(model=TestModel()),
            pytest.raises(LLMOutputError),
        ):
            run_agent_sync(agent, _settings(), user_prompt="u")

    def test_real_model_is_rejected_by_guard(self):
        """conftest のガードが有効なら実モデルへのリクエストは送られない."""
        with pytest.raises(RuntimeError, match="ALLOW_MODEL_REQUESTS"):
            run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")


@pytest.mark.unit
class TestStreamRequestContract:
    """ストリーミングで LiteLLM へ送る HTTP 本文の契約."""

    @pytest.mark.parametrize("alias", ALIASES)
    def test_stream_any_alias_sends_expected_body(self, fake_litellm, alias):
        """本文の項目は固定され、system は deps で渡したものだけが届く."""
        fake = fake_litellm(litellm_stream("OK"))

        _stream(
            _settings(alias),
            user_prompt="今の質問",
            deps="システム {{weather}} <system>原文</system>",
            message_history=[
                ModelRequest(parts=[UserPromptPart(content="前の質問")]),
                ModelResponse(parts=[TextPart(content="前の回答")]),
            ],
            max_tokens=1024,
        )

        assert fake.bodies == [
            {
                "model": alias,
                "stream": True,
                "stream_options": {"include_usage": True},
                "messages": [
                    {
                        "role": "system",
                        "content": "システム {{weather}} <system>原文</system>",
                    },
                    {"role": "user", "content": "前の質問"},
                    {"role": "assistant", "content": "前の回答"},
                    {"role": "user", "content": "今の質問"},
                ],
                "max_tokens": 1024,
                "metadata": {"service_name": "talk", "environment": "test-env"},
            }
        ]

    def test_stream_without_max_tokens_omits_max_tokens(self, fake_litellm):
        """max_tokens 未指定なら本文に載せない."""
        fake = fake_litellm(litellm_stream("OK"))

        _stream()

        assert "max_tokens" not in fake.bodies[0]
        assert "max_completion_tokens" not in fake.bodies[0]

    def test_stream_uses_proxy_url_key_and_timeout(self, fake_litellm):
        """接続先・キー・タイムアウトは LLMSettings の値を使う."""
        fake = fake_litellm(litellm_stream("OK"))

        _stream()

        request = fake.requests[0]
        assert str(request.url) == f"{BASE_URL}/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-test-key"
        assert request.extensions["timeout"]["read"] == 33


@pytest.mark.unit
class TestStreamResponseContract:
    """LiteLLM のストリーミング応答の解釈の契約."""

    @pytest.mark.parametrize(
        "chunks",
        [
            ("こん", "にち", "は"),
            ("  \n", "本文 ", "\n\n続き \n"),
            ("before<think>x</think>after",),
            ("wrap with <think> and ", "</think> tags"),
            ("<thinking>考え</thinking>本文",),
        ],
    )
    def test_chunks_concatenate_verbatim(self, fake_litellm, chunks):
        """増分を連結すると本文になり、空白も思考タグの文字列もそのまま残る."""
        fake_litellm(litellm_stream(*chunks))

        assert "".join(_stream()) == "".join(chunks)

    def test_chunks_with_gap_arrive_as_separate_deltas(self, fake_litellm):
        """デバウンスの幅より間隔が空いたチャンクは別の増分になる."""
        fake_litellm(litellm_stream("一", "二", gap=0.12))

        assert _stream() == ["一", "二"]

    def test_chunks_without_gap_are_grouped(self, fake_litellm):
        """デバウンスの幅に収まったチャンクは 1 つの増分にまとまる."""
        fake_litellm(litellm_stream("一", "二", "三"))

        assert _stream() == ["一二三"]

    def test_reasoning_content_is_not_mixed_into_stream(self, fake_litellm):
        """推論テキストは本文に混ぜない."""
        fake_litellm(litellm_stream({"reasoning_content": "考え中"}, "本文"))

        assert _stream() == ["本文"]

    def test_partial_text_cut_by_token_limit_is_streamed(self, fake_litellm):
        """出力上限で途中まででも本文があれば流す."""
        fake_litellm(litellm_stream("途中まで", finish_reason="length"))

        assert _stream() == ["途中まで"]

    @pytest.mark.parametrize(
        ("deltas", "finish_reason"),
        [
            (({"role": "assistant"},), "stop"),
            (({"role": "assistant", "content": None},), "stop"),
            (({"role": "assistant", "content": ""},), "stop"),
            (({"role": "assistant"},), "length"),
            (({"role": "assistant", "content": ""},), "length"),
            (({"reasoning_content": "考えるだけで上限に達した"},), "length"),
            (({"role": "assistant"},), "content_filter"),
            (({"role": "assistant", "refusal": "お答えできません"},), "stop"),
            (({"reasoning_content": "考えただけで終わった"},), "stop"),
        ],
    )
    def test_response_without_text_yields_nothing_without_retry(
        self, fake_litellm, deltas, finish_reason
    ):
        """本文がなければ理由によらず増分なしで正常終了し、再試行しない."""
        fake = fake_litellm(litellm_stream(*deltas, finish_reason=finish_reason))

        assert _stream() == []
        assert len(fake.requests) == 1
        assert fake.clients[0].is_closed()


@pytest.mark.unit
class TestStreamErrors:
    """ストリーミングの失敗はプロジェクトの例外になる."""

    @pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 502, 503])
    def test_status_error_raises_llm_client_error(self, fake_litellm, status):
        """HTTP エラーは LLMClientError になる."""
        fake_litellm(httpx2.Response(status, json={"error": {"message": "x"}}))

        with pytest.raises(LLMClientError) as exc_info:
            _stream()

        assert type(exc_info.value) is LLMClientError

    def test_read_timeout_on_open_raises_llm_timeout_error(self, fake_litellm):
        """開始前のタイムアウトは LLMTimeoutError になる."""
        fake_litellm(httpx2.ReadTimeout("slow"))

        with pytest.raises(LLMTimeoutError):
            _stream()

    def test_connect_error_raises_llm_client_error(self, fake_litellm):
        """接続失敗は LLMClientError になる."""
        fake_litellm(httpx2.ConnectError("refused"))

        with pytest.raises(LLMClientError) as exc_info:
            _stream()

        assert type(exc_info.value) is LLMClientError

    def test_read_timeout_midway_raises_after_partial_text(self, fake_litellm):
        """途中のタイムアウトは、届いた増分を流した後で LLMTimeoutError になる."""
        fake_litellm(
            litellm_stream("途中", "続き", gap=0.12, raises=httpx2.ReadTimeout("slow"))
        )
        received = []

        with pytest.raises(LLMTimeoutError):
            for text in stream_text_sync(
                _stream_agent(), _settings(), user_prompt="u", deps="s"
            ):
                received.append(text)

        assert received[0] == "途中"

    def test_connection_lost_midway_raises_llm_client_error(self, fake_litellm):
        """途中で接続が切れると LLMClientError になる."""
        fake_litellm(
            litellm_stream("途中", raises=httpx2.RemoteProtocolError("peer closed"))
        )

        with pytest.raises(LLMClientError) as exc_info:
            _stream()

        assert type(exc_info.value) is LLMClientError

    def test_error_chunk_midway_raises_llm_client_error(self, fake_litellm):
        """200 の後に届くエラーチャンクは LLMClientError になる."""
        fake_litellm(
            litellm_stream(
                "途中",
                finish_reason=None,
                raw=b'data: {"error": {"message": "boom", "code": 500}}\n\n',
            )
        )

        with pytest.raises(LLMClientError) as exc_info:
            _stream()

        assert type(exc_info.value) is LLMClientError

    def test_undecodable_chunk_raises_llm_client_error(self, fake_litellm):
        """JSON でないチャンクは LLMClientError 系になる."""
        fake_litellm(litellm_stream(finish_reason=None, raw=b"data: not json\n\n"))

        with pytest.raises(LLMClientError):
            _stream()

    def test_empty_stream_raises_llm_output_error(self, fake_litellm):
        """チャンクが 1 つもない応答は LLMOutputError になる."""
        fake_litellm(litellm_stream(finish_reason=None))

        with pytest.raises(LLMOutputError):
            _stream()

    def test_real_model_is_rejected_by_guard(self):
        """conftest のガードが有効なら実モデルへのリクエストは送られない."""
        with pytest.raises(RuntimeError, match="ALLOW_MODEL_REQUESTS"):
            _stream()


@pytest.mark.unit
class TestStreamLifecycle:
    """クライアントとストリームの開閉."""

    def test_nothing_is_requested_until_iterated(self, fake_litellm):
        """ジェネレータを作っただけでは接続しない."""
        fake = fake_litellm(litellm_stream("OK"))

        stream_text_sync(_stream_agent(), _settings(), user_prompt="u", deps="s")

        assert fake.clients == []
        assert fake.requests == []

    def test_client_is_closed_after_stream(self, fake_litellm):
        """接続はループに属するので実行ごとに閉じる."""
        fake = fake_litellm(litellm_stream("1"), litellm_stream("2"))

        assert _stream() == ["1"]
        assert _stream() == ["2"]

        assert len(fake.clients) == 2
        assert all(client.is_closed() for client in fake.clients)

    def test_client_is_closed_when_stream_fails(self, fake_litellm):
        """失敗時も閉じる."""
        fake = fake_litellm(httpx2.Response(500, json={"error": "boom"}))

        with pytest.raises(LLMClientError):
            _stream()

        assert fake.clients[0].is_closed()

    def test_client_is_closed_when_stream_fails_midway(self, fake_litellm):
        """途中で失敗しても HTTP の本文とクライアントを閉じる."""
        body = LiteLLMStreamBody("途中", raises=httpx2.ReadError("reset"))
        fake = fake_litellm(body.response())

        with pytest.raises(LLMClientError):
            _stream()

        assert body.closed
        assert fake.clients[0].is_closed()

    def test_close_midway_closes_http_stream_and_client(self, fake_litellm):
        """途中で閉じると、HTTP の本文とクライアントがその場で閉じる."""
        body = LiteLLMStreamBody("途中", hang=True)
        fake = fake_litellm(body.response())
        stream = stream_text_sync(
            _stream_agent(), _settings(), user_prompt="u", deps="s"
        )

        assert next(stream) == "途中"
        assert not body.closed
        stream.close()

        assert body.closed
        assert fake.clients[0].is_closed()

    def test_close_before_iteration_does_not_connect(self, fake_litellm):
        """開始前に閉じれば接続しない."""
        fake = fake_litellm(litellm_stream("OK"))
        stream = stream_text_sync(
            _stream_agent(), _settings(), user_prompt="u", deps="s"
        )

        stream.close()

        assert fake.clients == []

    def test_next_stream_works_after_close_midway(self, fake_litellm):
        """途中で閉じても、同じスレッド（同じループ）で次の実行に影響しない."""
        fake_litellm(
            LiteLLMStreamBody("途中", hang=True).response(), litellm_stream("次")
        )
        stream = stream_text_sync(
            _stream_agent(), _settings(), user_prompt="u", deps="s"
        )
        next(stream)
        stream.close()

        assert _stream() == ["次"]

    def test_run_agent_sync_works_on_same_thread_after_stream(self, fake_litellm):
        """同じスレッドで、ストリームの後に同期実行できる（タイトル生成と同じ流れ）."""
        fake_litellm(litellm_stream("本文"), litellm_response("タイトル"))

        assert _stream() == ["本文"]
        result = run_agent_sync(Agent(name="contract"), _settings(), user_prompt="u")

        assert result.output == "タイトル"

    def test_stream_works_on_thread_without_event_loop(self, fake_litellm):
        """イベントループのないスレッドでも動く（runserver のリクエストスレッド）."""
        fake_litellm(litellm_stream("本文"))
        outcome: dict[str, object] = {}

        def run() -> None:
            try:
                outcome["deltas"] = _stream()
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=30)

        assert outcome == {"deltas": ["本文"]}

    def test_stream_from_running_event_loop_is_rejected(self, fake_litellm):
        """イベントループの上からは使えず、接続もしない（呼び出し側の実装ミス）."""
        fake = fake_litellm(litellm_stream("OK"))

        async def call() -> list[str]:
            return _stream()

        with pytest.raises(RuntimeError, match="event loop"):
            async_to_sync(call)()

        assert fake.requests == []


@pytest.mark.unit
class TestStreamOptions:
    """stream_text_sync の引数の受け渡し."""

    def _conversation_id_seen_by(self, **kwargs) -> str:
        agent = Agent(name="contract", deps_type=str, output_type=str | None)
        seen: dict[str, str] = {}

        @agent.instructions
        def system_prompt(ctx: RunContext[str]) -> str:
            seen["conversation_id"] = ctx.conversation_id
            return ctx.deps

        list(stream_text_sync(agent, _settings(), user_prompt="u", deps="s", **kwargs))
        return seen["conversation_id"]

    def test_conversation_id_defaults_to_service_name(self, fake_litellm):
        """会話 ID の既定はサービス名で、実行ごとに変わらない（arun_agent と同じ）."""
        fake_litellm(litellm_stream("a"))

        assert self._conversation_id_seen_by() == _settings().service_name

    def test_conversation_id_can_be_specified(self, fake_litellm):
        """会話 ID を指定すると、その値で実行する."""
        fake_litellm(litellm_stream("a"))

        assert self._conversation_id_seen_by(conversation_id="chat/1") == "chat/1"

    def test_override_model_is_used(self):
        """Agent.override のモデルで実行できる（テストの差し替え）."""
        agent = _stream_agent()

        with agent.override(model=TestModel(custom_output_text="差し替え")):
            deltas = list(
                stream_text_sync(agent, _settings(), user_prompt="u", deps="s")
            )

        assert "".join(deltas) == "差し替え"

    def test_user_error_is_not_translated(self):
        """実装ミス（テキスト出力でないエージェント）は変換しない."""

        class Analysis(BaseModel):
            title: str

        agent = Agent(name="contract", output_type=Analysis)

        with (
            agent.override(model=TestModel()),
            pytest.raises(UserError),
        ):
            list(stream_text_sync(agent, _settings(), user_prompt="u"))


@pytest.mark.django_db
@pytest.mark.integration
def test_run_agent_sync_tool_sees_uncommitted_data():
    """ツール内の ORM は呼び出し元の DB 接続を使い、未コミットのデータが見える."""
    user_model = get_user_model()
    user_model.objects.create_user(
        email="uncommitted@example.com", password="x12345678"
    )
    agent = Agent(name="contract")

    @agent.tool
    async def count_users(ctx: RunContext[None]) -> int:
        """数える."""

        def count() -> int:
            return user_model.objects.filter(email="uncommitted@example.com").count()

        return await sync_to_async(count)()

    with agent.override(model=TestModel()):
        result = run_agent_sync(agent, _settings(), user_prompt="u")

    assert '"count_users":1' in result.output.replace(" ", "")


@pytest.mark.unit
def test_instrumentation_settings_are_shared_between_runs():
    """起動時に作った計装設定を共有し、実行ごとに作らない.

    `True` だと実行のたびに `InstrumentationSettings()` が作られ、MeterProvider が
    未設定の間は OpenTelemetry の `_ProxyMeterProvider` に Meter がたまり続ける。
    """
    agent = Agent(name="contract")

    assert isinstance(Agent._instrument_default, InstrumentationSettings)
    with (
        agent.override(model=TestModel()),
        patch.object(
            InstrumentationSettings,
            "__init__",
            side_effect=AssertionError("実行ごとに作られた"),
        ),
    ):
        run_agent_sync(agent, _settings(), user_prompt="u")


@pytest.mark.unit
def test_llm_settings_repr_hides_api_key():
    """接続設定の repr に API キーを出さない."""
    assert "sk-test-key" not in repr(_settings())
