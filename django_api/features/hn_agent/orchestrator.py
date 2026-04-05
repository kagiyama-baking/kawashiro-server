"""Orchestrator — Function CallingベースでSub-Agentを制御."""

import json
import logging
from typing import Any

from langfuse import observe

from integrations.llm.openai_client import OpenAIClient

from .agents.detective import DetectiveAgent
from .agents.hypothesis import HypothesisAgent
from .agents.memory import MemoryAgent
from .models import HNThread
from .prompts import get_prompt
from .reporter import Reporter
from .tools import ORCHESTRATOR_TOOLS

logger = logging.getLogger(__name__)

MAX_STEPS = 10

ORCHESTRATOR_SYSTEM_PROMPT = """あなたはHacker Newsの調査オーケストレーターです。
急上昇中のHNスレッドについて、利用可能なツールを使って調査を行います。

## 調査フロー
1. まずmemory_searchで過去に類似するスレッドがなかったか確認する
2. detective_investigateでスレッドの急上昇原因を調査する
3. コメント内で意見が明確に割れている場合はhypothesis_analyzeで対立主張を検証する
4. 全ての調査が完了したら、ツールを呼ばずに最終的なサマリーを日本語で返す

## 注意事項
- 各ツールは1回ずつ呼べば十分です
- hypothesis_analyzeは意見対立が明確な場合にのみ使ってください
- 調査完了後はツールを呼ばずにテキストで結論を返してください"""


class Orchestrator:
    """Function CallingベースでMemory/Detective Agentを制御するオーケストレーター."""

    def __init__(
        self,
        openai_client: OpenAIClient | None = None,
        memory_agent: MemoryAgent | None = None,
        detective_agent: DetectiveAgent | None = None,
        hypothesis_agent: HypothesisAgent | None = None,
        reporter: Reporter | None = None,
    ):
        """初期化."""
        self._openai_client = openai_client
        self._memory_agent = memory_agent
        self._detective_agent = detective_agent
        self._hypothesis_agent = hypothesis_agent
        self._reporter = reporter

    @property
    def openai_client(self) -> OpenAIClient:
        """OpenAIクライアントを取得（遅延初期化）."""
        if self._openai_client is None:
            self._openai_client = OpenAIClient()
        return self._openai_client

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
    def hypothesis_agent(self) -> HypothesisAgent:
        """Hypothesis Agentを取得（遅延初期化）."""
        if self._hypothesis_agent is None:
            self._hypothesis_agent = HypothesisAgent()
        return self._hypothesis_agent

    @property
    def reporter(self) -> Reporter:
        """Reporterを取得（遅延初期化）."""
        if self._reporter is None:
            self._reporter = Reporter()
        return self._reporter

    @observe(name="orchestrator.investigate")
    def investigate(self, thread: HNThread) -> dict[str, Any]:
        """スレッドの調査をオーケストレーション.

        Function Callingループで自律的にAgent呼び出しを決定する。

        Args:
            thread: 調査対象スレッド

        Returns:
            調査結果のサマリー
        """
        logger.info(
            "Orchestrator開始: [%d] %s",
            thread.hn_id,
            thread.title,
        )

        snapshot = thread.latest_snapshot
        score_info = ""
        if snapshot:
            score_info = (
                f"スコア: {snapshot.score}, コメント数: {snapshot.num_comments}"
            )

        system_prompt = get_prompt("hn-orchestrator-system", ORCHESTRATOR_SYSTEM_PROMPT)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"以下のHNスレッドを調査してください。\n\n"
                    f"HN ID: {thread.hn_id}\n"
                    f"タイトル: {thread.title}\n"
                    f"URL: {thread.url or '(self-post)'}\n"
                    f"投稿者: {thread.author}\n"
                    f"{score_info}"
                ),
            },
        ]

        results: dict[str, Any] = {
            "thread_hn_id": thread.hn_id,
            "thread_title": thread.title,
            "steps": [],
            "memory_result": None,
            "detective_result": None,
            "hypothesis_result": None,
            "final_summary": "",
        }

        for step in range(MAX_STEPS):
            logger.info("Orchestrator step %d/%d", step + 1, MAX_STEPS)

            # 最初の2ステップはツール使用を強制し、LLMがテキストで
            # 回答を生成するのを防ぐ。3ステップ目以降はautoに切り替えて
            # LLMが結論を出せるようにする。
            tool_choice = "required" if step < 2 else "auto"

            try:
                response = self.openai_client.chat_completion(
                    messages=messages,
                    tools=ORCHESTRATOR_TOOLS,
                    tool_choice=tool_choice,
                )
            except Exception:
                logger.exception(
                    "Orchestrator LLM呼び出しエラー: [%d] step=%d",
                    thread.hn_id,
                    step + 1,
                )
                results["final_summary"] = "LLM呼び出しエラーにより調査を中断しました。"
                break

            # ツール呼び出しがない = LLMが結論を出した
            if not response.tool_calls:
                results["final_summary"] = response.content or ""
                results["steps"].append(
                    {
                        "step": step + 1,
                        "action": "conclusion",
                        "content": response.content,
                    }
                )
                logger.info("Orchestrator完了: 結論に到達 (step %d)", step + 1)
                break

            # ツール呼び出しを処理
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
            )

            for tool_call in response.tool_calls:
                tool_name = tool_call.function.name
                tool_result = self._execute_tool(tool_name, thread)

                results["steps"].append(
                    {
                        "step": step + 1,
                        "action": tool_name,
                        "success": tool_result is not None,
                    }
                )

                if tool_name == "memory_search":
                    results["memory_result"] = tool_result
                elif tool_name == "detective_investigate":
                    results["detective_result"] = tool_result
                elif tool_name == "hypothesis_analyze":
                    results["hypothesis_result"] = tool_result

                # Observationをメッセージに追加
                observation = json.dumps(
                    tool_result or {"error": "ツール実行に失敗しました"},
                    ensure_ascii=False,
                    default=str,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": observation[:3000],
                    }
                )
        else:
            logger.warning(
                "Orchestrator: 最大ステップ数に到達 [%d]",
                thread.hn_id,
            )
            results["final_summary"] = "最大ステップ数に到達しました。"

        # Slack通知
        self._send_notifications(results)

        logger.info(
            "Orchestrator終了: [%d] %d steps",
            thread.hn_id,
            len(results["steps"]),
        )
        return results

    def _execute_tool(self, tool_name: str, thread: HNThread) -> dict[str, Any] | None:
        """ツールを実行.

        Args:
            tool_name: ツール名
            thread: 対象スレッド

        Returns:
            ツール実行結果。失敗時はNone
        """
        try:
            if tool_name == "memory_search":
                logger.info("Memory Agent実行: [%d]", thread.hn_id)
                return self.memory_agent.investigate(thread)

            if tool_name == "detective_investigate":
                logger.info("Detective Agent実行: [%d]", thread.hn_id)
                return self.detective_agent.investigate(thread)

            if tool_name == "hypothesis_analyze":
                logger.info("Hypothesis Agent実行: [%d]", thread.hn_id)
                return self.hypothesis_agent.investigate(thread)

            logger.warning("未知のツール: %s", tool_name)
            return None
        except Exception:
            logger.exception("ツール実行エラー: %s [%d]", tool_name, thread.hn_id)
            return None

    def _send_notifications(self, results: dict[str, Any]) -> None:
        """調査結果をSlackに通知."""
        if results.get("memory_result"):
            self.reporter.report_memory(results["memory_result"])

        if results.get("detective_result"):
            self.reporter.report_detective(results["detective_result"])

        if results.get("hypothesis_result"):
            self.reporter.report_hypothesis(results["hypothesis_result"])
