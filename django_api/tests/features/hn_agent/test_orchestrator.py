"""Orchestrator（PydanticAI エージェント）のテスト."""

import asyncio
import inspect
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from features.hn_agent.agents.detective import DETECTIVE_AGENT, DetectiveAgent
from features.hn_agent.agents.devils_advocate import (
    DEVILS_ADVOCATE_AGENT,
    DevilsAdvocateAgent,
)
from features.hn_agent.agents.security_responder import (
    SECURITY_RESPONDER_AGENT,
    SecurityResponderAgent,
)
from features.hn_agent.models import HNThread, HNThreadSnapshot
from features.hn_agent.orchestrator import MAX_STEPS, ORCHESTRATOR_AGENT, Orchestrator
from integrations.hn.client import HNComment
from tests.fixtures.langfuse import FakeLangfuse
from tests.fixtures.llm import ScriptedLLM, litellm_response, tool_calls

pytestmark = pytest.mark.django_db

FIXED_ERROR_SUMMARY = "LLM呼び出しエラーにより調査を中断しました。"
# プロンプトを Langfuse から取れず、調査を始めなかったときの final_summary
PROMPT_UNAVAILABLE_SUMMARY = "プロンプトを取得できないため調査を中断しました。"
ORCHESTRATOR_LOGGER = "features.hn_agent.orchestrator"
# サブエージェント（Detective・Devil's Advocate・Security Responder）の 6 本の Langfuse のプロンプト名
SUBAGENT_PROMPT_NAMES = (
    "hn-agent-detective",
    "hn-agent-detective-user",
    "hn-agent-devils-advocate",
    "hn-agent-devils-advocate-user",
    "hn-agent-security-responder",
    "hn-agent-security-responder-user",
)

# Langfuse 上のプロンプトはこの名前と説明を前提に書かれている（変更時はプロンプトも直す）
TOOL_DESCRIPTIONS = {
    "detective_investigate": (
        "スレッドが急上昇している理由を汎用的に調査する。\n"
        "タイトル和訳、注目理由、背景情報、HNコメントのハイライトを整理する。\n"
        "一般的なニュース・話題性のある記事で使う。"
    ),
    "devils_advocate_analyze": (
        "新しい技術・プロダクト発表（Show HN）、アーキテクチャ議論など、\n"
        "新規性の高いスレッドに対して HN民の辛口・批判的な視点を抽出する。\n"
        "懸念点・トレードオフ・過去の類似事例・批判的コメントを整理する。\n"
        "detective_investigate と併用することが多い。"
    ),
    "security_responder_analyze": (
        "脆弱性・CVE・情報漏洩・ハッキング・ゼロデイなど、セキュリティ\n"
        "インシデントのスレッドに対して、影響範囲・回避策・公式パッチ・CVE ID\n"
        "を整理してエンジニアの対応方針を明確化する。\n"
        "セキュリティ話題ではこのツール単独で完結させてよい（detective は不要）。"
    ),
}


@pytest.fixture
def orchestrator_llm(hn_llm_services, hn_agent_config):
    """Orchestrator の LLM 応答を台本で固定する."""
    llm = ScriptedLLM()
    with ORCHESTRATOR_AGENT.override(model=llm.model):
        yield llm


@pytest.fixture
def thread():
    """テスト用スレッド."""
    t = HNThread.objects.create(
        hn_id=700,
        title="Test Orchestrator Thread",
        url="https://example.com/orch",
        author="testuser",
    )
    HNThreadSnapshot.objects.create(thread=t, score=200, num_comments=50)
    return t


@pytest.fixture
def mock_detective_agent():
    """モックDetective Agent."""
    agent = MagicMock()
    agent.investigate = AsyncMock(
        return_value={
            "thread_hn_id": 700,
            "thread_title": "Test Orchestrator Thread",
            "thread_url": "https://example.com/orch",
            "score_info": "スコア: 200, コメント数: 50",
            "analysis": {"title_ja": "テスト", "why_trending": "テスト"},
            "background_sources": [],
            "comments_analyzed": 5,
        }
    )
    return agent


@pytest.fixture
def mock_devils_advocate_agent():
    """モックDevil's Advocate Agent."""
    agent = MagicMock()
    agent.analyze = AsyncMock(
        return_value={
            "thread_hn_id": 700,
            "thread_title": "Test Orchestrator Thread",
            "analysis": {
                "concerns": ["懸念1"],
                "past_cases": [],
                "critical_comments": [],
                "summary": "辛口総括",
            },
            "comments_analyzed": 3,
        }
    )
    return agent


@pytest.fixture
def mock_security_responder_agent():
    """モックSecurity Responder Agent."""
    agent = MagicMock()
    agent.analyze = AsyncMock(
        return_value={
            "thread_hn_id": 700,
            "thread_title": "Test Orchestrator Thread",
            "analysis": {
                "cve_ids": ["CVE-2025-0001"],
                "affected": ["lib 1.0"],
                "workarounds": [],
                "official_patch": {"available": False, "version": None, "url": None},
                "severity": "high",
                "summary": "回避策を適用",
            },
            "search_sources": [],
            "comments_analyzed": 4,
        }
    )
    return agent


@pytest.fixture
def mock_reporter():
    """モックReporter."""
    reporter = MagicMock()
    reporter.report_detective.return_value = True
    reporter.report_devils_advocate.return_value = True
    reporter.report_security_responder.return_value = True
    return reporter


@pytest.fixture
def orchestrator(
    mock_detective_agent,
    mock_devils_advocate_agent,
    mock_security_responder_agent,
    mock_reporter,
):
    """サブエージェントと Reporter をモックした Orchestrator."""
    return Orchestrator(
        detective_agent=mock_detective_agent,
        devils_advocate_agent=mock_devils_advocate_agent,
        security_responder_agent=mock_security_responder_agent,
        reporter=mock_reporter,
    )


def _tool_returns(request) -> dict[str, str]:
    """リクエストに含まれるツールの戻り値を {ツール名: 本文} で返す."""
    return {
        part.tool_name: part.content
        for message in request.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }


def _orchestrator_errors(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Orchestrator が出した ERROR のログのメッセージ."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == ORCHESTRATOR_LOGGER and record.levelno == logging.ERROR
    ]


def _prompt_error_log(thread: HNThread, prompt_name: str) -> str:
    """プロンプトを取れずに中断したときのログ（取れなかったプロンプトの名前と理由を含む）."""
    return (
        f"プロンプトを取得できないため調査を中断: [{thread.hn_id}] "
        f"プロンプト「{prompt_name}」を使えません（Langfuse からプロンプトを取得できませんでした: "
        f"{prompt_name} (label=production)）"
    )


@pytest.mark.integration
class TestOrchestrator:
    """Orchestratorのテスト."""

    def test_investigate_is_synchronous_and_returns_same_keys(
        self, orchestrator, orchestrator_llm, thread
    ):
        """同期シグネチャと戻り値のキーを維持する."""
        orchestrator_llm.enqueue("結論")

        result = orchestrator.investigate(thread)

        assert not inspect.iscoroutinefunction(Orchestrator.investigate)
        assert set(result) == {
            "thread_hn_id",
            "thread_title",
            "steps",
            "detective_result",
            "devils_advocate_result",
            "security_responder_result",
            "final_summary",
        }

    def test_orchestrator_completes_with_tool_calls(
        self,
        orchestrator,
        orchestrator_llm,
        thread,
        mock_detective_agent,
    ):
        """ツール呼び出し→結論のフローが正常に動作する."""
        orchestrator_llm.enqueue(
            tool_calls("detective_investigate"),
            "調査完了：テストスレッドの分析結果です。",
        )

        result = orchestrator.investigate(thread)

        assert result["thread_hn_id"] == 700
        assert result["final_summary"] == "調査完了：テストスレッドの分析結果です。"
        assert result["detective_result"] is not None
        assert len(result["steps"]) == 2
        assert result["steps"][0] == {
            "step": 1,
            "action": "detective_investigate",
            "success": True,
        }
        assert result["steps"][1] == {
            "step": 2,
            "action": "conclusion",
            "content": "調査完了：テストスレッドの分析結果です。",
        }

    def test_tool_body_runs_and_result_reaches_model(
        self,
        orchestrator,
        orchestrator_llm,
        thread,
        mock_detective_agent,
    ):
        """ツール本体が実際に走り、結果の JSON がモデルに渡る."""
        orchestrator_llm.enqueue(tool_calls("detective_investigate"), "完了")

        result = orchestrator.investigate(thread)

        mock_detective_agent.investigate.assert_awaited_once_with(thread)
        expected = mock_detective_agent.investigate.return_value
        assert result["detective_result"] == expected
        sent = _tool_returns(orchestrator_llm.requests[1])["detective_investigate"]
        assert json.loads(sent) == expected
        assert "テスト" in sent  # ensure_ascii=False のまま

    def test_orchestrator_immediate_conclusion(
        self, orchestrator, orchestrator_llm, thread
    ):
        """LLMがツールを呼ばずに即座に結論を出すケース."""
        orchestrator_llm.enqueue("このスレッドは既に調査済みです。")

        result = orchestrator.investigate(thread)

        assert len(result["steps"]) == 1
        assert result["steps"][0]["action"] == "conclusion"
        assert result["final_summary"] == "このスレッドは既に調査済みです。"

    def test_orchestrator_handles_llm_error(
        self, orchestrator, orchestrator_llm, thread
    ):
        """LLMエラー時にフォールバックメッセージを返す."""
        orchestrator_llm.enqueue(RuntimeError("LLM connection failed"))

        result = orchestrator.investigate(thread)

        assert "エラー" in result["final_summary"]
        assert result["final_summary"] == FIXED_ERROR_SUMMARY
        assert result["steps"] == []

    def test_orchestrator_handles_http_error(
        self, orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """LLM の HTTP エラーでも固定文を返し、通知も調査済みマークもしない."""
        orchestrator_llm.enqueue(ModelHTTPError(503, "test-alias"))

        result = orchestrator.investigate(thread)

        assert result["final_summary"] == FIXED_ERROR_SUMMARY
        mock_reporter.report_detective.assert_not_called()
        thread.refresh_from_db()
        assert thread.is_investigated is False

    def test_missing_llm_config_returns_fixed_summary(
        self, orchestrator, thread, hn_agent_config
    ):
        """LLM 設定がなくても例外にせず固定文を返す."""
        result = orchestrator.investigate(thread)

        assert result["final_summary"] == FIXED_ERROR_SUMMARY

    @pytest.mark.parametrize(
        "prompt_name", ["hn-agent-orchestrator", "hn-agent-orchestrator-user"]
    )
    def test_missing_orchestrator_prompt_aborts_without_llm_request_or_notification(
        self,
        orchestrator,
        orchestrator_llm,
        thread,
        mock_detective_agent,
        mock_reporter,
        hn_langfuse_prompts,
        caplog,
        prompt_name,
    ):
        """Orchestrator のプロンプトを Langfuse から取れなければ、LLM を呼ばずに調査を中断する.

        フォールバックはない。調査済みにしない（次のポーリングで再び調査する）ので、Slack へも
        送らない。ログには、LLM の失敗ではなく、どのプロンプトを取れなかったかを出す。
        """
        del hn_langfuse_prompts[(prompt_name, "production")]

        result = orchestrator.investigate(thread)

        assert orchestrator_llm.requests == []
        assert result["final_summary"] == PROMPT_UNAVAILABLE_SUMMARY
        mock_detective_agent.investigate.assert_not_awaited()
        mock_reporter.report_detective.assert_not_called()
        thread.refresh_from_db()
        assert thread.is_investigated is False
        assert _orchestrator_errors(caplog) == [_prompt_error_log(thread, prompt_name)]

    @pytest.mark.parametrize("prompt_name", SUBAGENT_PROMPT_NAMES)
    def test_missing_subagent_prompt_aborts_before_llm_and_hn_tavily_requests(
        self,
        orchestrator_llm,
        thread,
        mock_reporter,
        hn_langfuse_prompts,
        caplog,
        prompt_name,
    ):
        """サブエージェントのプロンプトが 1 本でも取れなければ、LLM も HN・Tavily も呼ばずに中断する.

        ツールの中で初めて失敗すると、HN・Tavily を呼んだ後に Orchestrator の LLM がもう一度
        呼ばれ、調査済みにならないのでポーリングのたびに繰り返す。サブエージェントは本物
        （HN・Tavily のクライアントだけ代役）にし、3 つのツールを呼ぶ台本にする。
        """
        hn_client = MagicMock()
        hn_client.get_comments.return_value = []
        hn_client.flatten_comments.return_value = []
        tavily_client = MagicMock()
        tavily_client.search_context.return_value = []
        orchestrator = Orchestrator(
            detective_agent=DetectiveAgent(
                hn_client=hn_client, tavily_client=tavily_client
            ),
            devils_advocate_agent=DevilsAdvocateAgent(hn_client=hn_client),
            security_responder_agent=SecurityResponderAgent(
                hn_client=hn_client, tavily_client=tavily_client
            ),
            reporter=mock_reporter,
        )
        orchestrator_llm.enqueue(
            tool_calls(
                "detective_investigate",
                "devils_advocate_analyze",
                "security_responder_analyze",
            ),
            "結論",
        )
        del hn_langfuse_prompts[(prompt_name, "production")]

        result = orchestrator.investigate(thread)

        assert orchestrator_llm.requests == []
        hn_client.get_comments.assert_not_called()
        tavily_client.search_context.assert_not_called()
        assert result["final_summary"] == PROMPT_UNAVAILABLE_SUMMARY
        assert result["steps"] == []
        mock_reporter.report_detective.assert_not_called()
        thread.refresh_from_db()
        assert thread.is_investigated is False
        assert _orchestrator_errors(caplog) == [_prompt_error_log(thread, prompt_name)]

    def test_usage_limit_exceeded_returns_fixed_summary(
        self,
        orchestrator,
        orchestrator_llm,
        thread,
        mock_detective_agent,
        mock_reporter,
    ):
        """ツールを呼び続けても上限で止まり、固定文を返す（完了済みの結果は通知する）."""
        orchestrator_llm.enqueue(
            *[tool_calls("detective_investigate") for _ in range(MAX_STEPS + 5)]
        )

        result = orchestrator.investigate(thread)

        assert result["final_summary"] == FIXED_ERROR_SUMMARY
        assert result["steps"] == []
        assert mock_detective_agent.investigate.await_count == MAX_STEPS
        assert len(orchestrator_llm.requests) == MAX_STEPS + 1
        mock_reporter.report_detective.assert_called_once()
        thread.refresh_from_db()
        assert thread.is_investigated is True

    def test_empty_final_response_leaves_summary_empty_without_retry(
        self, orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """ツール後の応答に本文がなくても再試行せず、結論なしで終える."""
        orchestrator_llm.enqueue(
            tool_calls("detective_investigate"),
            ModelResponse(parts=[TextPart(content="")]),
        )

        result = orchestrator.investigate(thread)

        assert result["final_summary"] == ""
        assert [s["action"] for s in result["steps"]] == ["detective_investigate"]
        assert len(orchestrator_llm.requests) == 2
        mock_reporter.report_detective.assert_called_once()

    def test_text_alongside_tool_call_is_not_a_conclusion(
        self, orchestrator, orchestrator_llm, thread
    ):
        """ツール呼び出しと同時のテキストは結論として扱わない."""
        orchestrator_llm.enqueue(
            ModelResponse(
                parts=[
                    TextPart(content="調べます"),
                    ToolCallPart(tool_name="detective_investigate", args={}),
                ]
            ),
            "結論",
        )

        result = orchestrator.investigate(thread)

        assert [s["action"] for s in result["steps"]] == [
            "detective_investigate",
            "conclusion",
        ]
        assert result["final_summary"] == "結論"

    def test_unknown_tool_name_is_reported_back_and_run_continues(
        self, orchestrator, orchestrator_llm, thread
    ):
        """未知のツール名は回数の上限まで続行し、モデルの結論を受け取る（従来と同じ）."""
        orchestrator_llm.enqueue(
            tool_calls("no_such_tool"), tool_calls("no_such_tool"), "結論"
        )

        result = orchestrator.investigate(thread)

        assert result["final_summary"] == "結論"
        assert [s["action"] for s in result["steps"]] == [
            "no_such_tool",
            "no_such_tool",
            "conclusion",
        ]

    def test_unknown_tool_name_repeated_stops_with_fixed_summary(
        self, orchestrator, orchestrator_llm, thread
    ):
        """未知のツール名を呼び続けても上限で止まり、固定文を返す."""
        orchestrator_llm.enqueue(
            *[tool_calls("no_such_tool") for _ in range(MAX_STEPS + 5)]
        )

        result = orchestrator.investigate(thread)

        assert result["final_summary"] == FIXED_ERROR_SUMMARY
        assert len(orchestrator_llm.requests) <= MAX_STEPS + 1

    def test_orchestrator_sends_notifications(
        self, orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """調査結果がSlack通知される."""
        orchestrator_llm.enqueue(tool_calls("detective_investigate"), "調査完了")

        orchestrator.investigate(thread)

        mock_reporter.report_detective.assert_called_once()

    def test_investigate_by_default_creates_reporter_and_notifies(
        self, mock_detective_agent, orchestrator_llm, thread
    ):
        """既定では Reporter を遅延生成して通知する（定期実行と一括実行）."""
        orchestrator = Orchestrator(detective_agent=mock_detective_agent)
        orchestrator_llm.enqueue(tool_calls("detective_investigate"), "結論")

        with patch("features.hn_agent.orchestrator.Reporter") as reporter_class:
            orchestrator.investigate(thread)

        reporter_class.assert_called_once_with()
        reporter_class.return_value.report_detective.assert_called_once()

    def test_investigate_with_notify_false_does_not_create_reporter(
        self, mock_detective_agent, orchestrator_llm, thread
    ):
        """notify=False なら結果があっても Reporter を作らない（Slack へ送らない）."""
        orchestrator = Orchestrator(detective_agent=mock_detective_agent, notify=False)
        orchestrator_llm.enqueue(tool_calls("detective_investigate"), "結論")

        with patch("features.hn_agent.orchestrator.Reporter") as reporter_class:
            result = orchestrator.investigate(thread)

        assert result["detective_result"] is not None
        reporter_class.assert_not_called()

    def test_investigate_with_notify_false_does_not_use_given_reporter(
        self, mock_detective_agent, mock_reporter, orchestrator_llm, thread
    ):
        """notify=False なら渡された Reporter も呼ばない."""
        orchestrator = Orchestrator(
            detective_agent=mock_detective_agent, reporter=mock_reporter, notify=False
        )
        orchestrator_llm.enqueue(tool_calls("detective_investigate"), "結論")

        orchestrator.investigate(thread)

        mock_reporter.report_detective.assert_not_called()

    def test_orchestrator_calls_detective_and_devils_advocate(
        self, orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """新技術スレッドで detective + devils_advocate が両方呼ばれる."""
        orchestrator_llm.enqueue(
            tool_calls("detective_investigate"),
            tool_calls("devils_advocate_analyze"),
            "完了",
        )

        result = orchestrator.investigate(thread)

        actions = [s["action"] for s in result["steps"]]
        assert "detective_investigate" in actions
        assert "devils_advocate_analyze" in actions
        assert [s["step"] for s in result["steps"]] == [1, 2, 3]
        mock_reporter.report_detective.assert_called_once()
        mock_reporter.report_devils_advocate.assert_called_once()
        mock_reporter.report_security_responder.assert_not_called()

    def test_orchestrator_security_only(
        self, orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """セキュリティ話題では security_responder のみ呼ばれる."""
        orchestrator_llm.enqueue(
            tool_calls("security_responder_analyze"), "対応方針を提示"
        )

        result = orchestrator.investigate(thread)

        assert result["security_responder_result"] is not None
        assert result["detective_result"] is None
        mock_reporter.report_security_responder.assert_called_once()
        mock_reporter.report_detective.assert_not_called()
        mock_reporter.report_devils_advocate.assert_not_called()

        # security_responder 単独でも調査済みマークが付与される（無限ループ防止）
        thread.refresh_from_db()
        assert thread.is_investigated is True

    def test_orchestrator_no_tool_does_not_mark_investigated(
        self, orchestrator, orchestrator_llm, thread
    ):
        """どのツールも呼ばれなかった場合は is_investigated を更新しない."""
        orchestrator_llm.enqueue("調査対象外と判断しました。")

        orchestrator.investigate(thread)

        thread.refresh_from_db()
        assert thread.is_investigated is False

    @pytest.mark.parametrize(
        ("tool_name", "agent_fixture", "method", "result_key", "error"),
        [
            (
                "detective_investigate",
                "mock_detective_agent",
                "investigate",
                "detective_result",
                "Detective Agent実行に失敗しました",
            ),
            (
                "devils_advocate_analyze",
                "mock_devils_advocate_agent",
                "analyze",
                "devils_advocate_result",
                "Devil's Advocate Agent実行に失敗しました",
            ),
            (
                "security_responder_analyze",
                "mock_security_responder_agent",
                "analyze",
                "security_responder_result",
                "Security Responder Agent実行に失敗しました",
            ),
        ],
    )
    def test_tool_failure_returns_error_json_and_marks_step_failed(
        self,
        request,
        orchestrator,
        orchestrator_llm,
        thread,
        mock_reporter,
        tool_name,
        agent_fixture,
        method,
        result_key,
        error,
    ):
        """サブエージェントの失敗はツール内で error JSON にし、ステップを失敗にする."""
        agent = request.getfixturevalue(agent_fixture)
        getattr(agent, method).side_effect = RuntimeError("boom")
        orchestrator_llm.enqueue(tool_calls(tool_name), "失敗を報告します")

        result = orchestrator.investigate(thread)

        assert result[result_key] is None
        assert result["steps"][0] == {
            "step": 1,
            "action": tool_name,
            "success": False,
        }
        assert result["final_summary"] == "失敗を報告します"
        sent = _tool_returns(orchestrator_llm.requests[1])[tool_name]
        assert json.loads(sent) == {"error": error}
        thread.refresh_from_db()
        assert thread.is_investigated is False
        mock_reporter.report_detective.assert_not_called()

    def test_request_uses_prompts_and_orchestrator_settings(
        self, orchestrator, orchestrator_llm, thread, hn_langfuse_prompts
    ):
        """プロンプトと LLM 設定は Orchestrator のものを使い、出力上限は付けない.

        system は Langfuse の本文そのまま、user は本文にスレッドの変数を差し込んだもの。
        """
        orchestrator_llm.enqueue("結論")

        orchestrator.investigate(thread)

        request = orchestrator_llm.requests[0]
        assert (
            request.instructions
            == hn_langfuse_prompts[("hn-agent-orchestrator", "production")]
        )
        assert request.user_prompt == (
            "HN ID: 700\nタイトル: Test Orchestrator Thread\n"
            "URL: https://example.com/orch\n投稿者: testuser\n"
            "スコア: 200, コメント数: 50"
        )
        settings = request.model_settings
        assert settings["extra_body"]["metadata"]["service_name"] == "orchestrator"
        assert "max_tokens" not in settings

    @pytest.mark.parametrize(
        ("configured", "expected"),
        [("low", "low"), ("medium", "medium"), ("high", "high"), ("", None)],
    )
    def test_request_uses_configured_reasoning_effort(
        self,
        orchestrator,
        orchestrator_llm,
        thread,
        hn_agent_config,
        configured,
        expected,
    ):
        """推論深度は有効な HNAgentConfig の値を使い、「無効」なら指定しない."""
        hn_agent_config.reasoning_effort = configured
        hn_agent_config.save()
        orchestrator_llm.enqueue("結論")

        orchestrator.investigate(thread)

        settings = orchestrator_llm.requests[0].model_settings
        assert settings.get("openai_reasoning_effort") == expected

    def test_tool_names_and_descriptions_match_prompt_contract(
        self, orchestrator, orchestrator_llm, thread
    ):
        """ツール名と説明は Langfuse プロンプトとの契約なので変えない."""
        orchestrator_llm.enqueue("結論")

        orchestrator.investigate(thread)

        tools = orchestrator_llm.requests[0].function_tools
        assert {tool.name: tool.description for tool in tools} == TOOL_DESCRIPTIONS
        for tool in tools:
            assert tool.parameters_json_schema["properties"] == {}

    def test_finalize_trace_records_decision_log(
        self,
        orchestrator,
        orchestrator_llm,
        thread,
        mock_detective_agent,
        hn_langfuse_prompts,
    ):
        """判断フローを現在のスパンに記録する."""
        mock_detective_agent.investigate.side_effect = RuntimeError("boom")
        orchestrator_llm.enqueue(tool_calls("detective_investigate"), "結論")
        client = MagicMock()
        # プロンプトは、差し替えたクライアントからも Langfuse の代役の本文を取る
        client.get_prompt.side_effect = FakeLangfuse(hn_langfuse_prompts).get_prompt

        with patch("langfuse.get_client", return_value=client):
            orchestrator.investigate(thread)

        metadata = client.update_current_span.call_args.kwargs["metadata"]
        assert metadata["total_steps"] == 2
        assert metadata["agents_called"] == ["detective_investigate"]
        assert metadata["decision_log"] == [
            "Step 1: detective_investigate を実行 → 失敗",
            "Step 2: 結論を出力",
        ]


@pytest.mark.integration
class TestOrchestratorThroughHTTP:
    """モデルの応答の解釈まで通すテスト（HTTP 層だけを差し替える）."""

    @pytest.mark.parametrize(
        "arguments", ["{}", "", "null", "[]", '{"hn_id": 700}', "{bad"]
    )
    def test_tool_runs_whatever_arguments_model_sends(
        self,
        fake_litellm,
        orchestrator,
        thread,
        mock_detective_agent,
        mock_reporter,
        hn_llm_services,
        hn_agent_config,
        arguments,
    ):
        """ツールは引数を取らないので、モデルが送る引数によらず実行する."""
        fake = fake_litellm(
            litellm_response(
                None,
                finish_reason="tool_calls",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "detective_investigate",
                            "arguments": arguments,
                        },
                    }
                ],
            ),
            litellm_response("結論"),
        )

        result = orchestrator.investigate(thread)

        mock_detective_agent.investigate.assert_awaited_once_with(thread)
        assert result["final_summary"] == "結論"
        assert result["steps"][0]["success"] is True
        assert len(fake.requests) == 2
        mock_reporter.report_detective.assert_called_once()

    @pytest.mark.parametrize(
        ("content", "finish_reason"),
        [(None, "stop"), (None, "length"), (None, "content_filter"), ("", "length")],
    )
    def test_conclusion_without_text_leaves_summary_empty(
        self,
        fake_litellm,
        orchestrator,
        thread,
        mock_reporter,
        hn_llm_services,
        hn_agent_config,
        content,
        finish_reason,
    ):
        """結論に本文がなくても例外にせず、ステップと通知はそのまま（従来と同じ）."""
        fake_litellm(
            litellm_response(
                None,
                finish_reason="tool_calls",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "detective_investigate",
                            "arguments": "{}",
                        },
                    }
                ],
            ),
            litellm_response(content, finish_reason=finish_reason),
        )

        result = orchestrator.investigate(thread)

        assert result["final_summary"] == ""
        assert [s["action"] for s in result["steps"]] == ["detective_investigate"]
        mock_reporter.report_detective.assert_called_once()

    def test_sub_agent_response_not_received_marks_tool_failed(
        self,
        fake_litellm,
        thread,
        mock_reporter,
        hn_llm_services,
        hn_agent_config,
    ):
        """不正な 200 応答はフォールバックせずツールの失敗にし、調査済みにしない."""
        hn_client = MagicMock()
        hn_client.get_comments.return_value = []
        hn_client.flatten_comments.return_value = []
        tavily_client = MagicMock()
        tavily_client.search_context.return_value = []
        orchestrator = Orchestrator(
            detective_agent=DetectiveAgent(
                hn_client=hn_client, tavily_client=tavily_client
            ),
            reporter=mock_reporter,
        )
        fake_litellm(
            litellm_response(
                None,
                finish_reason="tool_calls",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "detective_investigate",
                            "arguments": "{}",
                        },
                    }
                ],
            ),
            httpx2.Response(200, text="<html>", headers={"content-type": "text/html"}),
            litellm_response("結論"),
        )

        result = orchestrator.investigate(thread)

        assert result["detective_result"] is None
        assert result["steps"][0]["success"] is False
        mock_reporter.report_detective.assert_not_called()
        thread.refresh_from_db()
        assert thread.is_investigated is False

    def test_reasoning_effort_is_sent_only_in_orchestrator_requests(
        self,
        fake_litellm,
        thread,
        mock_reporter,
        hn_llm_services,
        hn_agent_config,
    ):
        """推論深度は Orchestrator の送信本文にだけ載り、サブエージェントには送らない."""
        hn_agent_config.reasoning_effort = "medium"
        hn_agent_config.save()
        hn_client = MagicMock()
        hn_client.get_comments.return_value = []
        hn_client.flatten_comments.return_value = []
        tavily_client = MagicMock()
        tavily_client.search_context.return_value = []
        orchestrator = Orchestrator(
            detective_agent=DetectiveAgent(
                hn_client=hn_client, tavily_client=tavily_client
            ),
            reporter=mock_reporter,
        )
        fake = fake_litellm(
            litellm_response(
                None,
                finish_reason="tool_calls",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "detective_investigate",
                            "arguments": "{}",
                        },
                    }
                ],
            ),
            litellm_response('{"title_ja": "和訳", "comment_highlights": []}'),
            litellm_response("結論"),
        )

        result = orchestrator.investigate(thread)

        assert result["detective_result"] is not None
        sent = [
            (body["metadata"]["service_name"], body.get("reasoning_effort"))
            for body in fake.bodies
        ]
        assert sent == [
            ("orchestrator", "medium"),
            ("detective", None),
            ("orchestrator", "medium"),
        ]


@pytest.mark.integration
class TestOrchestratorWithRealSubAgents:
    """サブエージェントも実物を使い、モデルだけを差し替えるテスト."""

    DETECTIVE_JSON = json.dumps(
        {"title_ja": "和訳", "comment_highlights": []}, ensure_ascii=False
    )
    ADVOCATE_JSON = json.dumps(
        {"concerns": ["懸念"], "critical_comments": []}, ensure_ascii=False
    )
    SECURITY_JSON = json.dumps(
        {"severity": "high", "summary": "対応"}, ensure_ascii=False
    )

    @pytest.fixture
    def mock_hn_client(self):
        """モックHNクライアント."""
        client = MagicMock()
        comments = [
            HNComment(
                hn_id=1,
                author="user1",
                text="Great!",
                parent_id=None,
                children=[],
            ),
        ]
        client.get_comments.return_value = comments
        client.flatten_comments.return_value = comments
        return client

    @pytest.fixture
    def mock_tavily_client(self):
        """検索結果のないモックTavilyクライアント."""
        client = MagicMock()
        client.search_context.return_value = []
        return client

    @pytest.fixture
    def real_orchestrator(self, mock_hn_client, mock_tavily_client, mock_reporter):
        """実物のサブエージェントを持つ Orchestrator."""
        return Orchestrator(
            detective_agent=DetectiveAgent(
                hn_client=mock_hn_client, tavily_client=mock_tavily_client
            ),
            devils_advocate_agent=DevilsAdvocateAgent(hn_client=mock_hn_client),
            security_responder_agent=SecurityResponderAgent(
                hn_client=mock_hn_client, tavily_client=mock_tavily_client
            ),
            reporter=mock_reporter,
        )

    def test_sub_agent_prompt_contains_uncommitted_data(
        self, real_orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """ツール内の ORM は呼び出し元の接続を使い、未コミットのデータが見える."""
        detective_llm = ScriptedLLM(self.DETECTIVE_JSON)
        orchestrator_llm.enqueue(tool_calls("detective_investigate"), "結論")

        with DETECTIVE_AGENT.override(model=detective_llm.model):
            result = real_orchestrator.investigate(thread)

        assert "スコア: 200, コメント数: 50" in detective_llm.requests[0].user_prompt
        assert result["detective_result"]["analysis"]["title_ja"] == "和訳"
        mock_reporter.report_detective.assert_called_once()
        thread.refresh_from_db()
        assert thread.is_investigated is True

    def test_two_tools_in_same_step_run_and_both_results_are_kept(
        self, real_orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """同じステップで 2 ツールが動き、準備処理の DB アクセスも壊れない."""
        detective_llm = ScriptedLLM(self.DETECTIVE_JSON)
        advocate_llm = ScriptedLLM(self.ADVOCATE_JSON)
        orchestrator_llm.enqueue(
            tool_calls("detective_investigate", "devils_advocate_analyze"),
            "両方完了",
        )

        with (
            DETECTIVE_AGENT.override(model=detective_llm.model),
            DEVILS_ADVOCATE_AGENT.override(model=advocate_llm.model),
        ):
            result = real_orchestrator.investigate(thread)

        assert result["detective_result"]["analysis"]["title_ja"] == "和訳"
        assert result["devils_advocate_result"]["analysis"]["concerns"] == ["懸念"]
        assert "スコア: 200" in detective_llm.requests[0].user_prompt
        assert "スコア: 200" in advocate_llm.requests[0].user_prompt
        assert result["steps"] == [
            {"step": 1, "action": "detective_investigate", "success": True},
            {"step": 2, "action": "devils_advocate_analyze", "success": True},
            {"step": 3, "action": "conclusion", "content": "両方完了"},
        ]
        returned = _tool_returns(orchestrator_llm.requests[1])
        assert set(returned) == {"detective_investigate", "devils_advocate_analyze"}
        mock_reporter.report_detective.assert_called_once()
        mock_reporter.report_devils_advocate.assert_called_once()

    def test_llm_calls_of_tools_in_same_step_overlap(
        self, real_orchestrator, orchestrator_llm, thread
    ):
        """同じステップの 2 ツールの LLM 呼び出しは並行に走る.

        片方の応答を、もう片方の呼び出しが始まるまで止める。直列なら待ち切れずに失敗する。
        """
        barrier = asyncio.Barrier(2)

        def waiting_model(text: str) -> FunctionModel:
            async def respond(messages, info) -> ModelResponse:
                await asyncio.wait_for(barrier.wait(), timeout=5)
                return ModelResponse(parts=[TextPart(content=text)])

            return FunctionModel(respond)

        orchestrator_llm.enqueue(
            tool_calls("detective_investigate", "devils_advocate_analyze"),
            "両方完了",
        )

        with (
            DETECTIVE_AGENT.override(model=waiting_model(self.DETECTIVE_JSON)),
            DEVILS_ADVOCATE_AGENT.override(model=waiting_model(self.ADVOCATE_JSON)),
        ):
            result = real_orchestrator.investigate(thread)

        assert result["detective_result"] is not None
        assert result["devils_advocate_result"] is not None

    def test_all_tools_in_one_step_with_one_failure_keeps_others(
        self, real_orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """並行実行の 1 つが失敗しても他の結果は残る."""
        detective_llm = ScriptedLLM(ModelHTTPError(500, "test-alias"))
        advocate_llm = ScriptedLLM(self.ADVOCATE_JSON)
        security_llm = ScriptedLLM(self.SECURITY_JSON)
        orchestrator_llm.enqueue(
            tool_calls(
                "detective_investigate",
                "devils_advocate_analyze",
                "security_responder_analyze",
            ),
            "一部失敗",
        )

        with (
            DETECTIVE_AGENT.override(model=detective_llm.model),
            DEVILS_ADVOCATE_AGENT.override(model=advocate_llm.model),
            SECURITY_RESPONDER_AGENT.override(model=security_llm.model),
        ):
            result = real_orchestrator.investigate(thread)

        assert result["detective_result"] is None
        assert result["devils_advocate_result"] is not None
        assert result["security_responder_result"] is not None
        assert [s.get("success") for s in result["steps"]] == [
            False,
            True,
            True,
            None,
        ]
        mock_reporter.report_detective.assert_not_called()
        thread.refresh_from_db()
        assert thread.is_investigated is True

    def test_unparsable_sub_agent_output_is_reported_with_fallback(
        self, real_orchestrator, orchestrator_llm, thread, mock_reporter
    ):
        """サブエージェントの応答を読めなくても調査済みにし、通知する（再調査しない）."""
        detective_llm = ScriptedLLM("JSONではない", "やはりJSONではない")
        orchestrator_llm.enqueue(tool_calls("detective_investigate"), "結論")

        with DETECTIVE_AGENT.override(model=detective_llm.model):
            result = real_orchestrator.investigate(thread)

        analysis = result["detective_result"]["analysis"]
        assert analysis["why_trending"] == "やはりJSONではない"
        mock_reporter.report_detective.assert_called_once()
        thread.refresh_from_db()
        assert thread.is_investigated is True


@pytest.mark.integration
class TestRunOrchestratorTask:
    """run_orchestratorタスクのテスト."""

    @patch("features.hn_agent.orchestrator.Orchestrator")
    def test_run_orchestrator_success(self, mock_orch_class):
        """正常にOrchestratorが実行される."""
        from features.hn_agent.tasks import run_orchestrator

        thread = HNThread.objects.create(hn_id=800, title="Task Test")

        mock_orch_class.return_value.investigate.return_value = {
            "steps": [{"step": 1, "action": "conclusion"}],
            "detective_result": None,
        }

        result = run_orchestrator(800)

        assert result["hn_id"] == 800
        assert result["steps"] == 1
        # 定期実行は通知する（notify=False を渡さない）
        mock_orch_class.assert_called_once_with()
        mock_orch_class.return_value.investigate.assert_called_once_with(thread)

    def test_run_orchestrator_thread_not_found(self):
        """存在しないスレッドIDでエラー結果を返す."""
        from features.hn_agent.tasks import run_orchestrator

        result = run_orchestrator(99999)

        assert "error" in result
