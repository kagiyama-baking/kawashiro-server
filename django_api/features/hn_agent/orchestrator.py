"""Orchestrator — LangGraph ReAct AgentでSub-Agentを制御."""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langfuse import observe
from langgraph.prebuilt import create_react_agent

from integrations.llm.config import get_llm_settings

from .agents.detective import DetectiveAgent
from .agents.memory import MemoryAgent
from .models import HNThread
from .prompts import get_prompt
from .reporter import Reporter

logger = logging.getLogger(__name__)

MAX_STEPS = 10

ORCHESTRATOR_SYSTEM_PROMPT = """あなたはHacker Newsの調査オーケストレーターです。
急上昇中のHNスレッドについて、利用可能なツールを使って調査を行います。

## 調査フロー
1. まずmemory_searchで過去に類似するスレッドがなかったか確認する
2. detective_investigateでスレッドの急上昇原因を調査する
3. 全ての調査が完了したら、ツールを呼ばずに最終的なサマリーを日本語で返す

## 注意事項
- 各ツールは1回ずつ呼べば十分です
- 調査完了後はツールを呼ばずにテキストで結論を返してください"""


class Orchestrator:
    """LangGraph ReAct AgentベースでMemory/Detective Agentを制御するオーケストレーター."""

    def __init__(
        self,
        memory_agent: MemoryAgent | None = None,
        detective_agent: DetectiveAgent | None = None,
        reporter: Reporter | None = None,
    ):
        """初期化."""
        self._memory_agent = memory_agent
        self._detective_agent = detective_agent
        self._reporter = reporter

    @property
    def memory_agent(self) -> MemoryAgent:
        """Memory Agentを取得（遅延初期化）."""
        if self._memory_agent is None:
            self._memory_agent = MemoryAgent()
        return self._memory_agent

    @property
    def detective_agent(self) -> DetectiveAgent:
        """Detective Agentを取得（遅延初期化）."""
        if self._detective_agent is None:
            self._detective_agent = DetectiveAgent()
        return self._detective_agent

    @property
    def reporter(self) -> Reporter:
        """Reporterを取得（遅延初期化）."""
        if self._reporter is None:
            self._reporter = Reporter()
        return self._reporter

    @observe(name="hn-agent/orchestrator")
    def investigate(self, thread: HNThread) -> dict[str, Any]:
        """スレッドの調査をオーケストレーション.

        LangGraph ReAct Agentがツール呼び出しを自律的に判断し、
        Memory/Detective Agentを実行する。

        Args:
            thread: 調査対象スレッド

        Returns:
            調査結果のサマリー
        """
        logger.info("Orchestrator開始: [%d] %s", thread.hn_id, thread.title)

        results: dict[str, Any] = {
            "thread_hn_id": thread.hn_id,
            "thread_title": thread.title,
            "steps": [],
            "memory_result": None,
            "detective_result": None,
            "final_summary": "",
        }

        try:
            agent_output = self._run_agent(thread, results)
            self._extract_results(agent_output, results)
        except Exception:
            logger.exception("Orchestrator LLM呼び出しエラー: [%d]", thread.hn_id)
            results["final_summary"] = "LLM呼び出しエラーにより調査を中断しました。"

        # Langfuseに判断フローを記録
        self._finalize_trace(thread, results)

        # Slack通知
        self._send_notifications(results)

        logger.info(
            "Orchestrator終了: [%d] %d steps",
            thread.hn_id,
            len(results["steps"]),
        )
        return results

    def _run_agent(self, thread: HNThread, results: dict[str, Any]) -> dict[str, Any]:
        """LangGraph ReAct Agentを構築・実行.

        Args:
            thread: 調査対象スレッド
            results: 結果を格納するdict（ツール実行時に更新される）

        Returns:
            LangGraphエージェントの出力state
        """
        settings = get_llm_settings("orchestrator")

        llm = ChatOpenAI(
            base_url=settings.proxy_base_url,
            api_key=settings.proxy_api_key,
            model=settings.model_alias,
            timeout=settings.timeout,
        )

        # ツールをクロージャとして定義（thread/resultsをキャプチャ）
        memory_agent = self.memory_agent
        detective_agent = self.detective_agent

        @tool
        def memory_search() -> str:
            """過去に類似するHNスレッドがあったか検索する。pgvectorのcosine similarityを使い、過去のスレッドと照合する。"""
            try:
                result = memory_agent.investigate(thread)
                results["memory_result"] = result
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                logger.exception("Memory Agent実行エラー: [%d]", thread.hn_id)
                return json.dumps({"error": "Memory Agent実行に失敗しました"})

        @tool
        def detective_investigate() -> str:
            """スレッドが急上昇している理由を調査する。HNコメント分析、Web検索、LLM総合分析を行う。"""
            try:
                result = detective_agent.investigate(thread)
                results["detective_result"] = result
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                logger.exception("Detective Agent実行エラー: [%d]", thread.hn_id)
                return json.dumps({"error": "Detective Agent実行に失敗しました"})

        tools = [memory_search, detective_investigate]
        agent = create_react_agent(llm, tools)

        # メッセージ構築
        system_prompt = get_prompt("hn-agent-orchestrator", ORCHESTRATOR_SYSTEM_PROMPT)
        user_content = self._build_user_message(thread)

        # Langfuseコールバック
        config: dict[str, Any] = {
            "recursion_limit": MAX_STEPS * 2 + 1,
        }
        langfuse_handler = self._get_langfuse_handler()
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]

        return agent.invoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_content),
                ]
            },
            config=config,
        )

    def _extract_results(
        self, agent_output: dict[str, Any], results: dict[str, Any]
    ) -> None:
        """LangGraphの出力からステップ情報と最終サマリーを抽出."""
        from langchain_core.messages import ToolMessage

        messages = agent_output.get("messages", [])
        step_num = 0

        for msg in messages:
            if isinstance(msg, AIMessage):
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        step_num += 1
                        results["steps"].append(
                            {
                                "step": step_num,
                                "action": tc["name"],
                                "success": True,
                            }
                        )
                elif msg.content:
                    step_num += 1
                    results["steps"].append(
                        {
                            "step": step_num,
                            "action": "conclusion",
                            "content": msg.content,
                        }
                    )
                    results["final_summary"] = msg.content

        # ToolMessageからエージェント結果を補完
        # （クロージャで既にセット済みの場合はスキップ）
        tool_result_map = {
            "memory_search": "memory_result",
            "detective_investigate": "detective_result",
        }
        for msg in messages:
            if isinstance(msg, ToolMessage) and msg.name in tool_result_map:
                result_key = tool_result_map[msg.name]
                if results[result_key] is None:
                    try:
                        parsed = json.loads(msg.content)
                        if "error" not in parsed:
                            results[result_key] = parsed
                    except (json.JSONDecodeError, TypeError):
                        pass

        # ツールエラーチェック
        for step in results["steps"]:
            action = step["action"]
            if action in tool_result_map:
                result_key = tool_result_map[action]
                if results[result_key] is None:
                    step["success"] = False

    def _build_user_message(self, thread: HNThread) -> str:
        """ユーザーメッセージを構築."""
        snapshot = thread.latest_snapshot
        score_info = ""
        if snapshot:
            score_info = (
                f"スコア: {snapshot.score}, コメント数: {snapshot.num_comments}"
            )

        return (
            f"以下のHNスレッドを調査してください。\n\n"
            f"HN ID: {thread.hn_id}\n"
            f"タイトル: {thread.title}\n"
            f"URL: {thread.url or '(self-post)'}\n"
            f"投稿者: {thread.author}\n"
            f"{score_info}"
        )

    def _get_langfuse_handler(self) -> Any:
        """Langfuseコールバックハンドラーを取得."""
        try:
            from langfuse.callback import CallbackHandler

            return CallbackHandler()
        except Exception:
            return None

    def _finalize_trace(self, thread: HNThread, results: dict[str, Any]) -> None:
        """Orchestratorの判断フローをLangfuseスパンに記録."""
        try:
            from langfuse import get_client

            client = get_client()

            decision_log = []
            for step_info in results.get("steps", []):
                action = step_info.get("action", "unknown")
                step_num = step_info.get("step", 0)

                if action == "conclusion":
                    entry = f"Step {step_num}: 結論を出力"
                else:
                    success = step_info.get("success", False)
                    status = "成功" if success else "失敗"
                    entry = f"Step {step_num}: {action} を実行 → {status}"

                decision_log.append(entry)

            client.update_current_span(
                metadata={
                    "thread_hn_id": thread.hn_id,
                    "thread_title": thread.title,
                    "total_steps": len(results.get("steps", [])),
                    "agents_called": [
                        s["action"]
                        for s in results.get("steps", [])
                        if s["action"] != "conclusion"
                    ],
                    "decision_log": decision_log,
                },
            )
        except Exception:
            pass  # Langfuse未設定時は無視

    def _send_notifications(self, results: dict[str, Any]) -> None:
        """調査結果をSlackに通知."""
        if results.get("memory_result"):
            self.reporter.report_memory(results["memory_result"])

        if results.get("detective_result"):
            self.reporter.report_detective(results["detective_result"])
