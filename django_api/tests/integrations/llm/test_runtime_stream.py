"""integrations.llm.runtime の stream_text_sync のテスト.

HTTP の契約は `httpx2.MockTransport` で OpenAI SDK の下まで通して確認する。
実ネットワークへは出ない。
"""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from asgiref.sync import async_to_sync
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.test import TestModel

from integrations.llm.config import LLMSettings
from integrations.llm.exceptions import (
    LLMClientError,
    LLMOutputError,
    LLMTimeoutError,
)
from integrations.llm.runtime import _close_client, run_agent_sync, stream_text_sync
from tests.fixtures.llm import LITELLM_ALIASES as ALIASES
from tests.fixtures.llm import LiteLLMStreamBody, litellm_response, litellm_stream
from tests.fixtures.sse import SEPARATE_DELTAS

BASE_URL = "http://litellm.invalid/v1"


def _settings(alias: str = "gpt-4o-mini") -> LLMSettings:
    return LLMSettings(
        proxy_base_url=BASE_URL,
        proxy_api_key="sk-test-key",
        model_alias=alias,
        timeout=33,
        service_name="talk",
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
        fake_litellm(litellm_stream("一", "二", gap=SEPARATE_DELTAS))

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
            litellm_stream(
                "途中", "続き", gap=SEPARATE_DELTAS, raises=httpx2.ReadTimeout("slow")
            )
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

    def test_client_close_failure_does_not_fail_stream(self, fake_litellm, caplog):
        """閉じるときの失敗は警告だけにする（本文はすでに返している）."""
        fake_litellm(litellm_stream("本文"))

        with patch.object(
            AsyncOpenAI, "close", AsyncMock(side_effect=RuntimeError("close failed"))
        ):
            assert _stream() == ["本文"]

        assert "close failed" in caplog.text

    def test_close_client_without_event_loop_does_nothing(self):
        """ループがなければ接続も開いていないので何もしない."""
        client = MagicMock()

        with patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")):
            _close_client(client)

        client.close.assert_not_called()


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
