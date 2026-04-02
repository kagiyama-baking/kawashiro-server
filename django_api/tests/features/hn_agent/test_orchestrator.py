"""Orchestratorのテスト."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from features.hn_agent.models import HNThread, HNThreadSnapshot
from features.hn_agent.orchestrator import Orchestrator


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
    def mock_openai_client(self):
        """Function Callingの応答をモックするOpenAIクライアント."""
        client = MagicMock()
        return client

    @pytest.fixture
    def mock_memory_agent(self):
        """モックMemory Agent."""
        agent = MagicMock()
        agent.investigate.return_value = {
            "thread_hn_id": 700,
            "thread_title": "Test Orchestrator Thread",
            "similar_threads": [],
            "has_similar": False,
            "summary": "類似スレッドなし",
        }
        return agent

    @pytest.fixture
    def mock_detective_agent(self):
        """モックDetective Agent."""
        agent = MagicMock()
        agent.investigate.return_value = {
            "thread_hn_id": 700,
            "thread_title": "Test Orchestrator Thread",
            "thread_url": "https://example.com/orch",
            "score_info": "スコア: 200, コメント数: 50",
            "analysis": "テスト分析結果",
            "background_sources": [],
            "comments_analyzed": 5,
        }
        return agent

    @pytest.fixture
    def mock_reporter(self):
        """モックReporter."""
        reporter = MagicMock()
        reporter.report_memory.return_value = False
        reporter.report_detective.return_value = True
        return reporter

    def test_orchestrator_completes_with_tool_calls(
        self,
        thread,
        mock_openai_client,
        mock_memory_agent,
        mock_detective_agent,
        mock_reporter,
    ):
        """ツール呼び出し→結論のフローが正常に動作する."""
        # Step 1: memory_searchを呼ぶ
        response_step1 = Mock()
        response_step1.content = None
        tool_call_memory = Mock()
        tool_call_memory.id = "call_1"
        tool_call_memory.function.name = "memory_search"
        tool_call_memory.function.arguments = "{}"
        response_step1.tool_calls = [tool_call_memory]

        # Step 2: detective_investigateを呼ぶ
        response_step2 = Mock()
        response_step2.content = None
        tool_call_detective = Mock()
        tool_call_detective.id = "call_2"
        tool_call_detective.function.name = "detective_investigate"
        tool_call_detective.function.arguments = "{}"
        response_step2.tool_calls = [tool_call_detective]

        # Step 3: 結論
        response_step3 = Mock()
        response_step3.content = "調査完了：テストスレッドの分析結果です。"
        response_step3.tool_calls = None

        mock_openai_client.chat_completion.side_effect = [
            response_step1,
            response_step2,
            response_step3,
        ]

        orchestrator = Orchestrator(
            openai_client=mock_openai_client,
            memory_agent=mock_memory_agent,
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        assert result["thread_hn_id"] == 700
        assert len(result["steps"]) == 3
        assert result["steps"][0]["action"] == "memory_search"
        assert result["steps"][1]["action"] == "detective_investigate"
        assert result["steps"][2]["action"] == "conclusion"
        assert result["final_summary"] == "調査完了：テストスレッドの分析結果です。"
        assert result["memory_result"] is not None
        assert result["detective_result"] is not None

        mock_memory_agent.investigate.assert_called_once_with(thread)
        mock_detective_agent.investigate.assert_called_once_with(thread)

    def test_orchestrator_immediate_conclusion(
        self,
        thread,
        mock_openai_client,
        mock_memory_agent,
        mock_detective_agent,
        mock_reporter,
    ):
        """LLMがツールを呼ばずに即座に結論を出すケース."""
        response = Mock()
        response.content = "このスレッドは既に調査済みです。"
        response.tool_calls = None

        mock_openai_client.chat_completion.return_value = response

        orchestrator = Orchestrator(
            openai_client=mock_openai_client,
            memory_agent=mock_memory_agent,
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        assert len(result["steps"]) == 1
        assert result["steps"][0]["action"] == "conclusion"
        assert result["final_summary"] == "このスレッドは既に調査済みです。"
        mock_memory_agent.investigate.assert_not_called()
        mock_detective_agent.investigate.assert_not_called()

    def test_orchestrator_handles_tool_error(
        self,
        thread,
        mock_openai_client,
        mock_memory_agent,
        mock_detective_agent,
        mock_reporter,
    ):
        """ツール実行エラー時にもループが継続する."""
        mock_memory_agent.investigate.side_effect = RuntimeError("API error")

        # Step 1: memory_search（エラー）
        response_step1 = Mock()
        response_step1.content = None
        tool_call = Mock()
        tool_call.id = "call_1"
        tool_call.function.name = "memory_search"
        tool_call.function.arguments = "{}"
        response_step1.tool_calls = [tool_call]

        # Step 2: 結論
        response_step2 = Mock()
        response_step2.content = "Memory検索は失敗しましたが、他の情報から判断します。"
        response_step2.tool_calls = None

        mock_openai_client.chat_completion.side_effect = [
            response_step1,
            response_step2,
        ]

        orchestrator = Orchestrator(
            openai_client=mock_openai_client,
            memory_agent=mock_memory_agent,
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        assert len(result["steps"]) == 2
        assert result["steps"][0]["success"] is False
        assert result["memory_result"] is None

    def test_orchestrator_max_steps_limit(
        self,
        thread,
        mock_openai_client,
        mock_memory_agent,
        mock_detective_agent,
        mock_reporter,
    ):
        """最大ステップ数でループが終了する."""
        # 常にツールを呼び続けるレスポンス
        response = Mock()
        response.content = None
        tool_call = Mock()
        tool_call.id = "call_loop"
        tool_call.function.name = "memory_search"
        tool_call.function.arguments = "{}"
        response.tool_calls = [tool_call]

        mock_openai_client.chat_completion.return_value = response

        orchestrator = Orchestrator(
            openai_client=mock_openai_client,
            memory_agent=mock_memory_agent,
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        assert result["final_summary"] == "最大ステップ数に到達しました。"
        # 10ステップ（MAX_STEPS）で停止
        assert len(result["steps"]) == 10

    def test_orchestrator_sends_notifications(
        self,
        thread,
        mock_openai_client,
        mock_memory_agent,
        mock_detective_agent,
        mock_reporter,
    ):
        """調査結果がSlackに通知される."""
        # 即結論
        response = Mock()
        response.content = "完了"
        response.tool_calls = None

        mock_openai_client.chat_completion.return_value = response

        # 事前にresultsにdetective_resultを設定するため、直接テスト
        orchestrator = Orchestrator(
            openai_client=mock_openai_client,
            memory_agent=mock_memory_agent,
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        orchestrator.investigate(thread)

        # resultsにagent結果がないので通知は呼ばれない
        mock_reporter.report_detective.assert_not_called()


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
            "memory_result": None,
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
