"""Orchestrator（LangGraph ReAct Agent）のテスト."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from features.hn_agent.models import HNThread, HNThreadSnapshot
from features.hn_agent.orchestrator import Orchestrator

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    """Langfuse 接続を外して resolve_prompt を fallback_text 経由にする."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.mark.integration
class TestOrchestrator:
    """Orchestratorのテスト."""

    @pytest.fixture
    def thread(self):
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
    def mock_detective_agent(self):
        """モックDetective Agent."""
        agent = MagicMock()
        agent.investigate.return_value = {
            "thread_hn_id": 700,
            "thread_title": "Test Orchestrator Thread",
            "thread_url": "https://example.com/orch",
            "score_info": "スコア: 200, コメント数: 50",
            "analysis": {"title_ja": "テスト", "why_trending": "テスト"},
            "background_sources": [],
            "comments_analyzed": 5,
        }
        return agent

    @pytest.fixture
    def mock_devils_advocate_agent(self):
        """モックDevil's Advocate Agent."""
        agent = MagicMock()
        agent.analyze.return_value = {
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
        return agent

    @pytest.fixture
    def mock_security_responder_agent(self):
        """モックSecurity Responder Agent."""
        agent = MagicMock()
        agent.analyze.return_value = {
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
        return agent

    @pytest.fixture
    def mock_reporter(self):
        """モックReporter."""
        reporter = MagicMock()
        reporter.report_detective.return_value = True
        reporter.report_devils_advocate.return_value = True
        reporter.report_security_responder.return_value = True
        return reporter

    def _make_agent_result(self, messages):
        """LangGraph agent.invoke()の結果を構築."""
        return {"messages": messages}

    @patch("features.hn_agent.orchestrator.create_react_agent")
    @patch("features.hn_agent.orchestrator.ChatOpenAI")
    @patch("features.hn_agent.orchestrator.get_llm_settings")
    def test_orchestrator_completes_with_tool_calls(
        self,
        mock_get_settings,
        mock_chat_class,
        mock_create_agent,
        thread,
        mock_detective_agent,
        mock_reporter,
        hn_agent_config,
    ):
        """ツール呼び出し→結論のフローが正常に動作する."""
        mock_get_settings.return_value = Mock(
            proxy_base_url="http://proxy:4000/v1",
            proxy_api_key="sk-test",
            model_alias="gpt-4o",
            timeout=60,
            service_name="orchestrator",
            environment="dev",
        )

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._make_agent_result(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "call_1", "name": "detective_investigate", "args": {}}
                    ],
                ),
                ToolMessage(
                    content='{"analysis": {"title_ja": "テスト"}}',
                    tool_call_id="call_1",
                    name="detective_investigate",
                ),
                AIMessage(content="調査完了：テストスレッドの分析結果です。"),
            ]
        )
        mock_create_agent.return_value = mock_agent

        orchestrator = Orchestrator(
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        assert result["thread_hn_id"] == 700
        assert result["final_summary"] == "調査完了：テストスレッドの分析結果です。"
        assert result["detective_result"] is not None
        assert len(result["steps"]) == 2
        assert result["steps"][0]["action"] == "detective_investigate"
        assert result["steps"][1]["action"] == "conclusion"

    @patch("features.hn_agent.orchestrator.create_react_agent")
    @patch("features.hn_agent.orchestrator.ChatOpenAI")
    @patch("features.hn_agent.orchestrator.get_llm_settings")
    def test_orchestrator_immediate_conclusion(
        self,
        mock_get_settings,
        mock_chat_class,
        mock_create_agent,
        thread,
        mock_detective_agent,
        mock_reporter,
        hn_agent_config,
    ):
        """LLMがツールを呼ばずに即座に結論を出すケース."""
        mock_get_settings.return_value = Mock(
            proxy_base_url="http://proxy:4000/v1",
            proxy_api_key="sk-test",
            model_alias="gpt-4o",
            timeout=60,
            service_name="orchestrator",
            environment="dev",
        )

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._make_agent_result(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user"),
                AIMessage(content="このスレッドは既に調査済みです。"),
            ]
        )
        mock_create_agent.return_value = mock_agent

        orchestrator = Orchestrator(
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        assert len(result["steps"]) == 1
        assert result["steps"][0]["action"] == "conclusion"
        assert result["final_summary"] == "このスレッドは既に調査済みです。"

    @patch("features.hn_agent.orchestrator.create_react_agent")
    @patch("features.hn_agent.orchestrator.ChatOpenAI")
    @patch("features.hn_agent.orchestrator.get_llm_settings")
    def test_orchestrator_handles_llm_error(
        self,
        mock_get_settings,
        mock_chat_class,
        mock_create_agent,
        thread,
        mock_detective_agent,
        mock_reporter,
        hn_agent_config,
    ):
        """LLMエラー時にフォールバックメッセージを返す."""
        mock_get_settings.return_value = Mock(
            proxy_base_url="http://proxy:4000/v1",
            proxy_api_key="sk-test",
            model_alias="gpt-4o",
            timeout=60,
            service_name="orchestrator",
            environment="dev",
        )

        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = RuntimeError("LLM connection failed")
        mock_create_agent.return_value = mock_agent

        orchestrator = Orchestrator(
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        assert "エラー" in result["final_summary"]

    @patch("features.hn_agent.orchestrator.create_react_agent")
    @patch("features.hn_agent.orchestrator.ChatOpenAI")
    @patch("features.hn_agent.orchestrator.get_llm_settings")
    def test_orchestrator_sends_notifications(
        self,
        mock_get_settings,
        mock_chat_class,
        mock_create_agent,
        thread,
        mock_detective_agent,
        mock_reporter,
        hn_agent_config,
    ):
        """調査結果がSlack通知される."""
        mock_get_settings.return_value = Mock(
            proxy_base_url="http://proxy:4000/v1",
            proxy_api_key="sk-test",
            model_alias="gpt-4o",
            timeout=60,
            service_name="orchestrator",
            environment="dev",
        )

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._make_agent_result(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "call_1", "name": "detective_investigate", "args": {}}
                    ],
                ),
                ToolMessage(
                    content='{"analysis": {"title_ja": "test"}}',
                    tool_call_id="call_1",
                    name="detective_investigate",
                ),
                AIMessage(content="調査完了"),
            ]
        )
        mock_create_agent.return_value = mock_agent

        orchestrator = Orchestrator(
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        orchestrator.investigate(thread)

        mock_reporter.report_detective.assert_called_once()

    @patch("features.hn_agent.orchestrator.create_react_agent")
    @patch("features.hn_agent.orchestrator.ChatOpenAI")
    @patch("features.hn_agent.orchestrator.get_llm_settings")
    def test_orchestrator_calls_detective_and_devils_advocate(
        self,
        mock_get_settings,
        mock_chat_class,
        mock_create_agent,
        thread,
        mock_detective_agent,
        mock_devils_advocate_agent,
        mock_security_responder_agent,
        mock_reporter,
        hn_agent_config,
    ):
        """新技術スレッドで detective + devils_advocate が両方呼ばれる."""
        mock_get_settings.return_value = Mock(
            proxy_base_url="http://proxy:4000/v1",
            proxy_api_key="sk-test",
            model_alias="gpt-4o",
            timeout=60,
            service_name="orchestrator",
            environment="dev",
        )

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._make_agent_result(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "c1", "name": "detective_investigate", "args": {}}
                    ],
                ),
                ToolMessage(
                    content='{"analysis": {"title_ja": "new"}}',
                    tool_call_id="c1",
                    name="detective_investigate",
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "c2", "name": "devils_advocate_analyze", "args": {}}
                    ],
                ),
                ToolMessage(
                    content='{"analysis": {"concerns": ["foo"]}}',
                    tool_call_id="c2",
                    name="devils_advocate_analyze",
                ),
                AIMessage(content="完了"),
            ]
        )
        mock_create_agent.return_value = mock_agent

        orchestrator = Orchestrator(
            detective_agent=mock_detective_agent,
            devils_advocate_agent=mock_devils_advocate_agent,
            security_responder_agent=mock_security_responder_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        actions = [s["action"] for s in result["steps"]]
        assert "detective_investigate" in actions
        assert "devils_advocate_analyze" in actions
        mock_reporter.report_detective.assert_called_once()
        mock_reporter.report_devils_advocate.assert_called_once()
        mock_reporter.report_security_responder.assert_not_called()

    @patch("features.hn_agent.orchestrator.create_react_agent")
    @patch("features.hn_agent.orchestrator.ChatOpenAI")
    @patch("features.hn_agent.orchestrator.get_llm_settings")
    def test_orchestrator_security_only(
        self,
        mock_get_settings,
        mock_chat_class,
        mock_create_agent,
        thread,
        mock_detective_agent,
        mock_devils_advocate_agent,
        mock_security_responder_agent,
        mock_reporter,
        hn_agent_config,
    ):
        """セキュリティ話題では security_responder のみ呼ばれる."""
        mock_get_settings.return_value = Mock(
            proxy_base_url="http://proxy:4000/v1",
            proxy_api_key="sk-test",
            model_alias="gpt-4o",
            timeout=60,
            service_name="orchestrator",
            environment="dev",
        )

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._make_agent_result(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "c1",
                            "name": "security_responder_analyze",
                            "args": {},
                        }
                    ],
                ),
                ToolMessage(
                    content='{"analysis": {"severity": "critical"}}',
                    tool_call_id="c1",
                    name="security_responder_analyze",
                ),
                AIMessage(content="対応方針を提示"),
            ]
        )
        mock_create_agent.return_value = mock_agent

        orchestrator = Orchestrator(
            detective_agent=mock_detective_agent,
            devils_advocate_agent=mock_devils_advocate_agent,
            security_responder_agent=mock_security_responder_agent,
            reporter=mock_reporter,
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

    @patch("features.hn_agent.orchestrator.create_react_agent")
    @patch("features.hn_agent.orchestrator.ChatOpenAI")
    @patch("features.hn_agent.orchestrator.get_llm_settings")
    def test_orchestrator_no_tool_does_not_mark_investigated(
        self,
        mock_get_settings,
        mock_chat_class,
        mock_create_agent,
        thread,
        mock_detective_agent,
        mock_devils_advocate_agent,
        mock_security_responder_agent,
        mock_reporter,
        hn_agent_config,
    ):
        """どのツールも呼ばれなかった場合は is_investigated を更新しない."""
        mock_get_settings.return_value = Mock(
            proxy_base_url="http://proxy:4000/v1",
            proxy_api_key="sk-test",
            model_alias="gpt-4o",
            timeout=60,
            service_name="orchestrator",
            environment="dev",
        )
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._make_agent_result(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user"),
                AIMessage(content="調査対象外と判断しました。"),
            ]
        )
        mock_create_agent.return_value = mock_agent

        orchestrator = Orchestrator(
            detective_agent=mock_detective_agent,
            devils_advocate_agent=mock_devils_advocate_agent,
            security_responder_agent=mock_security_responder_agent,
            reporter=mock_reporter,
        )
        orchestrator.investigate(thread)

        thread.refresh_from_db()
        assert thread.is_investigated is False


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
        mock_orch_class.return_value.investigate.assert_called_once_with(thread)

    def test_run_orchestrator_thread_not_found(self):
        """存在しないスレッドIDでエラー結果を返す."""
        from features.hn_agent.tasks import run_orchestrator

        result = run_orchestrator(99999)

        assert "error" in result
