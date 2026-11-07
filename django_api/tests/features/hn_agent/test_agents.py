"""Detective Agent と共通の分析実行のテスト."""

import json
from unittest.mock import MagicMock, patch

import httpx2
import pytest
from asgiref.sync import async_to_sync
from langfuse._utils.serializer import EventSerializer
from pydantic import BaseModel
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart

from features.hn_agent.agents import run_analysis
from features.hn_agent.agents.detective import DETECTIVE_AGENT, DetectiveAgent
from features.hn_agent.models import HNThread, HNThreadSnapshot
from integrations.hn.client import HNComment
from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMOutputError,
)
from integrations.llm.runtime import arun_agent
from tests.fixtures.llm import ScriptedLLM, litellm_response, make_llm_settings

pytestmark = pytest.mark.django_db


@pytest.fixture
def detective_llm(hn_llm_services):
    """Detective の LLM 応答を台本で固定する."""
    llm = ScriptedLLM()
    with DETECTIVE_AGENT.override(model=llm.model):
        yield llm


@pytest.mark.integration
class TestDetectiveAgent:
    """DetectiveAgentのテスト."""

    MOCK_ANALYSIS_JSON = json.dumps(
        {
            "title_ja": "テスト記事タイトル",
            "why_trending": "技術的に面白い内容のため。",
            "background": "著者はテスト分野の専門家。",
            "comment_highlights": [
                {
                    "author": "user1",
                    "quote": "素晴らしい記事だ",
                    "stance": "肯定",
                }
            ],
            "summary": "技術的関心が高い。",
        },
        ensure_ascii=False,
    )

    @pytest.fixture
    def mock_hn_client(self):
        """モックHNクライアント."""
        client = MagicMock()
        comments = [
            HNComment(
                hn_id=1,
                author="user1",
                text="Great article!",
                parent_id=None,
                children=[],
            ),
            HNComment(
                hn_id=2,
                author="user2",
                text="I disagree with this approach.",
                parent_id=None,
                children=[],
            ),
        ]
        client.get_comments.return_value = comments
        client.flatten_comments.return_value = comments
        return client

    @pytest.fixture
    def mock_tavily_client(self):
        """モックTavilyクライアント."""
        from integrations.tavily.client import TavilySearchResult

        client = MagicMock()
        client.search_context.return_value = [
            TavilySearchResult(
                title="Background Info",
                url="https://example.com/bg",
                content="Some background context about the topic.",
                score=0.9,
            )
        ]
        return client

    @pytest.fixture
    def hot_thread(self):
        """スナップショット付きのスレッド（pytest のトランザクション内で未コミット）."""
        thread = HNThread.objects.create(
            hn_id=600,
            title="Hot Thread",
            url="https://example.com/hot",
            author="author1",
        )
        HNThreadSnapshot.objects.create(thread=thread, score=200, num_comments=50)
        return thread

    @pytest.fixture
    def agent(self, mock_hn_client, mock_tavily_client):
        """HN と Tavily をモックした DetectiveAgent."""
        return DetectiveAgent(
            hn_client=mock_hn_client,
            tavily_client=mock_tavily_client,
        )

    def test_investigate_returns_structured_result(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """調査が完了し構造化結果を返す（is_investigated マークは Orchestrator の責務）."""
        detective_llm.enqueue(self.MOCK_ANALYSIS_JSON)

        result = async_to_sync(agent.investigate)(hot_thread)

        assert result["thread_hn_id"] == 600
        assert result["thread_title"] == "Hot Thread"
        assert result["thread_url"] == "https://example.com/hot"
        assert result["score_info"] == "スコア: 200, コメント数: 50"
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["title_ja"] == "テスト記事タイトル"
        assert result["comments_analyzed"] == 2
        assert len(result["background_sources"]) == 1
        hot_thread.refresh_from_db()
        assert hot_thread.is_investigated is False

    def test_investigate_without_tavily(
        self, mock_hn_client, detective_llm, hn_agent_config
    ):
        """Tavily未設定でも調査が完了する."""
        detective_llm.enqueue(self.MOCK_ANALYSIS_JSON)
        thread = HNThread.objects.create(
            hn_id=601, title="No Tavily Thread", author="author2"
        )

        agent = DetectiveAgent(hn_client=mock_hn_client, tavily_client=None)
        # tavily_clientプロパティがNoneを返すようにする
        with patch.object(
            type(agent), "tavily_client", new_callable=lambda: property(lambda s: None)
        ):
            result = async_to_sync(agent.investigate)(thread)

        assert result["background_sources"] == []
        assert isinstance(result["analysis"], dict)
        assert result["analysis"]["title_ja"] == "テスト記事タイトル"

    def test_investigate_prompt_contains_uncommitted_data(
        self, agent, hot_thread, detective_llm, hn_agent_config, hn_langfuse_prompts
    ):
        """準備処理は呼び出し元の DB 接続で動き、未コミットのデータがプロンプトに入る.

        system は Langfuse の本文そのまま、user は本文に変数を差し込んだもの。
        """
        detective_llm.enqueue(self.MOCK_ANALYSIS_JSON)

        async_to_sync(agent.investigate)(hot_thread)

        request = detective_llm.requests[0]
        assert request.user_prompt.startswith(
            "タイトル: Hot Thread\nURL: https://example.com/hot\n投稿者: author1\n"
            "スコア: 200, コメント数: 50\n"
        )
        assert "Background Info" in request.user_prompt
        assert "[user1]: Great article!" in request.user_prompt
        assert "{{" not in request.user_prompt
        assert (
            request.instructions
            == hn_langfuse_prompts[("hn-agent-detective", "production")]
        )

    def test_investigate_sends_detective_service_metadata(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """LLM 設定は detective のものを使う."""
        detective_llm.enqueue(self.MOCK_ANALYSIS_JSON)

        async_to_sync(agent.investigate)(hot_thread)

        metadata = detective_llm.requests[0].model_settings["extra_body"]["metadata"]
        assert metadata["service_name"] == "detective"

    def test_investigate_keeps_extra_keys_and_strips_code_fence(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """コードフェンス付きの JSON を読み、未知のキーも残す."""
        payload = {**json.loads(self.MOCK_ANALYSIS_JSON), "extra": {"k": 1}}
        detective_llm.enqueue(f"```json\n{json.dumps(payload)}\n```")

        result = async_to_sync(agent.investigate)(hot_thread)

        assert result["analysis"]["extra"] == {"k": 1}
        assert len(detective_llm.requests) == 1

    def test_investigate_keeps_only_keys_returned_by_llm(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """LLM が返していないキーを analysis に足さない（API の応答が変わらない）."""
        detective_llm.enqueue('{"title_ja": "題", "comment_highlights": []}')

        result = async_to_sync(agent.investigate)(hot_thread)

        assert result["analysis"] == {"title_ja": "題", "comment_highlights": []}

    def test_investigate_retries_invalid_output_once(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """読めない応答は 1 回だけ再試行する."""
        detective_llm.enqueue("JSONではない", self.MOCK_ANALYSIS_JSON)

        result = async_to_sync(agent.investigate)(hot_thread)

        assert result["analysis"]["title_ja"] == "テスト記事タイトル"
        assert len(detective_llm.requests) == 2

    def test_investigate_invalid_output_twice_returns_fallback(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """再試行でも読めなければ最後の応答の先頭 500 文字でフォールバックする."""
        detective_llm.enqueue("最初の応答", "あ" * 600)

        result = async_to_sync(agent.investigate)(hot_thread)

        assert result["analysis"] == {
            "title_ja": "",
            "why_trending": "あ" * 500,
            "background": "",
            "comment_highlights": [],
            "summary": "",
        }
        assert len(detective_llm.requests) == 2

    def test_investigate_missing_required_key_returns_fallback(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """必須キーのない JSON はフォールバックにする（従来の検査と同じ）."""
        no_required = json.dumps({"why_trending": "理由"}, ensure_ascii=False)
        detective_llm.enqueue(no_required, no_required)

        result = async_to_sync(agent.investigate)(hot_thread)

        assert result["analysis"]["why_trending"] == no_required
        assert result["analysis"]["comment_highlights"] == []

    def test_investigate_empty_output_returns_empty_fallback(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """本文のない応答が続けば空のフォールバックにする."""
        empty = ModelResponse(parts=[TextPart(content="")])
        detective_llm.enqueue(empty, empty)

        result = async_to_sync(agent.investigate)(hot_thread)

        assert result["analysis"]["why_trending"] == ""
        assert result["analysis"]["title_ja"] == ""

    def test_investigate_llm_error_is_raised(
        self, agent, hot_thread, detective_llm, hn_agent_config
    ):
        """接続エラーなどはフォールバックせず送出する（ツール側で error JSON にする）."""
        detective_llm.enqueue(ModelHTTPError(503, "test-alias"))

        with pytest.raises(LLMClientError):
            async_to_sync(agent.investigate)(hot_thread)

    def test_investigate_missing_llm_config_raises_configuration_error(
        self, agent, hot_thread, hn_agent_config
    ):
        """LLM 設定がなければ LLMConfigurationError を送出する."""
        with pytest.raises(LLMConfigurationError):
            async_to_sync(agent.investigate)(hot_thread)

    def test_observe_input_serialization_in_event_loop_keeps_model_fields(
        self, hot_thread
    ):
        """@observe の入力シリアライズはイベントループ上でもフィールドを記録できる.

        ORM に触れると SynchronousOnlyOperation になり、シリアライザが握りつぶすので
        フィールドが残らない。
        """

        async def serialize() -> str:
            return json.dumps(
                {"args": (hot_thread,), "kwargs": {}}, cls=EventSerializer
            )

        serialized = async_to_sync(serialize)()

        assert json.loads(serialized)["args"][0]["hn_id"] == 600

    def test_format_background_section_with_items(self, mock_hn_client):
        """背景情報が存在する場合はセクションヘッダと各項目が含まれる."""
        agent = DetectiveAgent(hn_client=mock_hn_client)

        section = agent._format_background_section(
            [
                {
                    "title": "BG",
                    "url": "https://bg.com",
                    "content": "background",
                }
            ]
        )

        assert "## Web上の背景情報" in section
        assert "BG" in section
        assert "https://bg.com" in section
        assert "background" in section

    def test_format_background_section_empty(self, mock_hn_client):
        """背景情報が空の場合は空文字を返す."""
        agent = DetectiveAgent(hn_client=mock_hn_client)
        assert agent._format_background_section([]) == ""

    def test_format_comments_section_with_text(self, mock_hn_client):
        """コメントがある場合はヘッダと内容が含まれる."""
        agent = DetectiveAgent(hn_client=mock_hn_client)

        section = agent._format_comments_section("[user1]: Hello")

        assert "## HNコメント（抜粋）" in section
        assert "<hn_comments>" in section
        assert "[user1]: Hello" in section
        assert "</hn_comments>" in section

    def test_format_comments_section_empty(self, mock_hn_client):
        """コメントが空の場合は空文字を返す."""
        agent = DetectiveAgent(hn_client=mock_hn_client)
        assert agent._format_comments_section("") == ""


@pytest.mark.unit
class TestRunAnalysis:
    """run_analysis のテスト."""

    class Analysis(BaseModel):
        """テスト用の出力スキーマ."""

        title: str

    @pytest.fixture
    def agent(self):
        """テスト用のエージェント."""
        return Agent(
            name="analysis-test",
            output_type=PromptedOutput(self.Analysis, template=False),
        )

    def _run(self, agent):
        return async_to_sync(run_analysis)(
            agent,
            make_llm_settings("detective"),
            "system",
            "user",
            lambda raw: {"fallback": raw},
            conversation_id="hn-thread/1",
        )

    def test_valid_output_returns_json_dict(self, agent):
        """検証済みの出力を JSON 互換の dict で返す."""
        llm = ScriptedLLM('{"title": "題"}')

        with agent.override(model=llm.model):
            analysis = self._run(agent)

        assert analysis == {"title": "題"}
        assert llm.requests[0].instructions == "system"
        assert llm.requests[0].user_prompt == "user"

    def test_invalid_output_calls_fallback_with_last_text(self, agent):
        """再試行後も不正ならフォールバックに最後の本文を渡す."""
        llm = ScriptedLLM("一度目", "二度目")

        with agent.override(model=llm.model):
            analysis = self._run(agent)

        assert analysis == {"fallback": "二度目"}

    def test_empty_last_response_uses_previous_text(self, agent):
        """最後の応答が空なら、その前の本文をフォールバックに渡す."""
        llm = ScriptedLLM("一度目", ModelResponse(parts=[TextPart(content="")]))

        with agent.override(model=llm.model):
            analysis = self._run(agent)

        assert analysis == {"fallback": "一度目"}

    def test_response_not_received_is_raised_instead_of_fallback(
        self, agent, fake_litellm
    ):
        """モデルの応答を受け取れていなければフォールバックしない（調査済みにしない）."""
        fake_litellm(
            httpx2.Response(200, text="<html>", headers={"content-type": "text/html"})
        )

        with pytest.raises(LLMOutputError):
            self._run(agent)

    def test_text_with_thinking_tags_is_validated_as_is(self, agent, fake_litellm):
        """JSON の文字列中の思考タグを切り取らずに検証する."""
        title = "uses <think> tag and </think> closes"
        fake_litellm(litellm_response(json.dumps({"title": title})))

        assert self._run(agent) == {"title": title}

    def test_output_cut_by_token_limit_retries_then_returns_fallback(
        self, agent, fake_litellm
    ):
        """本文なしで出力上限に達した応答も例外にせず、再試行の後でフォールバックする."""
        fake = fake_litellm(
            litellm_response(None, finish_reason="length"),
            litellm_response(None, finish_reason="length"),
        )

        assert self._run(agent) == {"fallback": ""}
        assert len(fake.requests) == 2

    def test_retry_and_request_limits_are_passed(self, agent):
        """出力リトライ 1 回、リクエスト上限 3 回で実行する."""
        llm = ScriptedLLM('{"title": "題"}')

        with (
            agent.override(model=llm.model),
            patch("features.hn_agent.agents.arun_agent", wraps=arun_agent) as mock_run,
        ):
            self._run(agent)

        kwargs = mock_run.call_args.kwargs
        assert kwargs["retries"] == {"output": 1}
        assert kwargs["usage_limits"].request_limit == 3
