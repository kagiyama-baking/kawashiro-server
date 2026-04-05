"""Orchestratorのテスト."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from features.hn_agent.models import HNThread, HNThreadSnapshot
from features.hn_agent.orchestrator import Orchestrator


@pytest.fixture(autouse=True)
def _mock_get_prompt():
    """テスト中はLangfuseプロンプト取得をフォールバックにする."""
    with patch(
        "features.hn_agent.orchestrator.get_prompt",
        side_effect=lambda name, fallback: fallback,
    ):
        yield


def _make_reasoning_item(text="テスト推論"):
    """Responses APIのreasoningアイテムを生成."""
    summary_part = Mock()
    summary_part.text = text
    item = Mock()
    item.type = "reasoning"
    item.summary = [summary_part]
    return item


def _make_function_call_item(name, call_id="call_1"):
    """Responses APIのfunction_callアイテムを生成."""
    item = Mock()
    item.type = "function_call"
    item.name = name
    item.arguments = "{}"
    item.call_id = call_id
    return item


def _make_message_item(text):
    """Responses APIのmessageアイテムを生成."""
    content_part = Mock()
    content_part.text = text
    item = Mock()
    item.type = "message"
    item.content = [content_part]
    return item


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
        """Responses APIの応答をモックするOpenAIクライアント."""
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
            "analysis": {"title_ja": "テスト", "why_trending": "テスト"},
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
        # Step 1: reasoning + memory_search
        response_step1 = Mock()
        response_step1.output = [
            _make_reasoning_item("過去に類似スレッドがないか確認する"),
            _make_function_call_item("memory_search", "call_1"),
        ]

        # Step 2: reasoning + detective_investigate
        response_step2 = Mock()
        response_step2.output = [
            _make_reasoning_item("急上昇原因を調査する"),
            _make_function_call_item("detective_investigate", "call_2"),
        ]

        # Step 3: reasoning + conclusion
        response_step3 = Mock()
        response_step3.output = [
            _make_reasoning_item("全調査完了、結論をまとめる"),
            _make_message_item("調査完了：テストスレッドの分析結果です。"),
        ]

        mock_openai_client.responses_create.side_effect = [
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
        assert result["steps"][0]["reasoning"] == "過去に類似スレッドがないか確認する"
        assert result["steps"][1]["action"] == "detective_investigate"
        assert result["steps"][1]["reasoning"] == "急上昇原因を調査する"
        assert result["steps"][2]["action"] == "conclusion"
        assert result["steps"][2]["reasoning"] == "全調査完了、結論をまとめる"
        assert result["final_summary"] == "調査完了：テストスレッドの分析結果です。"
        assert result["memory_result"] is not None
        assert result["detective_result"] is not None

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
        response.output = [
            _make_message_item("このスレッドは既に調査済みです。"),
        ]

        mock_openai_client.responses_create.return_value = response

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

    def test_orchestrator_records_reasoning(
        self,
        thread,
        mock_openai_client,
        mock_memory_agent,
        mock_detective_agent,
        mock_reporter,
    ):
        """reasoningが各ステップに記録される."""
        response_step1 = Mock()
        response_step1.output = [
            _make_reasoning_item("まず類似スレッドを検索すべき"),
            _make_function_call_item("memory_search", "call_1"),
        ]

        response_step2 = Mock()
        response_step2.output = [
            _make_message_item("完了"),
        ]

        mock_openai_client.responses_create.side_effect = [
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

        assert result["steps"][0]["reasoning"] == "まず類似スレッドを検索すべき"

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

        response_step1 = Mock()
        response_step1.output = [
            _make_function_call_item("memory_search", "call_1"),
        ]

        response_step2 = Mock()
        response_step2.output = [
            _make_message_item("Memory検索は失敗しましたが判断します。"),
        ]

        mock_openai_client.responses_create.side_effect = [
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
        response = Mock()
        response.output = [
            _make_function_call_item("memory_search", "call_loop"),
        ]

        mock_openai_client.responses_create.return_value = response

        orchestrator = Orchestrator(
            openai_client=mock_openai_client,
            memory_agent=mock_memory_agent,
            detective_agent=mock_detective_agent,
            reporter=mock_reporter,
        )

        result = orchestrator.investigate(thread)

        assert result["final_summary"] == "最大ステップ数に到達しました。"
        assert len(result["steps"]) == 10


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
