"""Orchestrator — Responses API + reasoningでSub-Agentを制御."""

import json
import logging
from typing import Any

from langfuse import observe

from integrations.llm.openai_client import OpenAIClient

from .agents.detective import DetectiveAgent
from .agents.memory import MemoryAgent
from .models import HNAgentConfig, HNThread
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
3. 全ての調査が完了したら、ツールを呼ばずに最終的なサマリーを日本語で返す

## 注意事項
- 各ツールは1回ずつ呼べば十分です
- 調査完了後はツールを呼ばずにテキストで結論を返してください"""


def _get_reasoning_effort() -> str | None:
    """HN Agent設定からreasoning effortを取得."""
    try:
        config = HNAgentConfig.objects.get_active_config()
        return config.reasoning_effort or None
    except HNAgentConfig.DoesNotExist:
        return "low"


class Orchestrator:
    """Responses APIベースでMemory/Detective Agentを制御するオーケストレーター."""

    def __init__(
        self,
        openai_client: OpenAIClient | None = None,
        memory_agent: MemoryAgent | None = None,
        detective_agent: DetectiveAgent | None = None,
        reporter: Reporter | None = None,
    ):
        """初期化."""
        self._openai_client = openai_client
        self._memory_agent = memory_agent
        self._detective_agent = detective_agent
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
    def reporter(self) -> Reporter:
        """Reporterを取得（遅延初期化）."""
        if self._reporter is None:
            self._reporter = Reporter()
        return self._reporter

    @observe(name="hn-agent/orchestrator")
    def investigate(self, thread: HNThread) -> dict[str, Any]:
        """スレッドの調査をオーケストレーション.

        Responses APIのreasoningでLLMの判断理由を記録しながら、
        自律的にAgent呼び出しを決定する。

        Args:
            thread: 調査対象スレッド

        Returns:
            調査結果のサマリー
        """
        logger.info("Orchestrator開始: [%d] %s", thread.hn_id, thread.title)

        snapshot = thread.latest_snapshot
        score_info = ""
        if snapshot:
            score_info = (
                f"スコア: {snapshot.score}, コメント数: {snapshot.num_comments}"
            )

        system_prompt = get_prompt("hn-agent-orchestrator", ORCHESTRATOR_SYSTEM_PROMPT)

        # Responses APIのinput_items構築
        input_items: list[Any] = [
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
            "final_summary": "",
        }

        reasoning_effort = _get_reasoning_effort()

        for step in range(MAX_STEPS):
            logger.info("Orchestrator step %d/%d", step + 1, MAX_STEPS)

            tool_choice = "required" if step < 2 else "auto"

            try:
                response = self.openai_client.responses_create(
                    input_items=input_items,
                    tools=ORCHESTRATOR_TOOLS,
                    tool_choice=tool_choice,
                    reasoning_effort=reasoning_effort,
                )
            except Exception:
                logger.exception(
                    "Orchestrator LLM呼び出しエラー: [%d] step=%d",
                    thread.hn_id,
                    step + 1,
                )
                results["final_summary"] = "LLM呼び出しエラーにより調査を中断しました。"
                break

            # response.outputからreasoning/function_call/messageを分離
            reasoning_text, function_calls, conclusion_text = (
                self._parse_response_output(response.output)
            )

            # reasoningがあればステップ情報に記録
            if reasoning_text:
                logger.info(
                    "Orchestrator reasoning (step %d): %s",
                    step + 1,
                    reasoning_text[:100],
                )

            # ツール呼び出しがない = LLMが結論を出した
            if not function_calls:
                results["final_summary"] = conclusion_text
                results["steps"].append(
                    {
                        "step": step + 1,
                        "action": "conclusion",
                        "content": conclusion_text,
                        "reasoning": reasoning_text,
                    }
                )
                logger.info("Orchestrator完了: 結論に到達 (step %d)", step + 1)
                break

            # response.outputの全アイテムをinput_itemsに追加
            # （reasoning itemsも含める — 省略するとAPIエラー）
            for item in response.output:
                input_items.append(item)

            # ツール実行 + 結果をinput_itemsに追加
            for fc in function_calls:
                tool_result = self._execute_tool(fc.name, thread)

                results["steps"].append(
                    {
                        "step": step + 1,
                        "action": fc.name,
                        "success": tool_result is not None,
                        "reasoning": reasoning_text,
                    }
                )

                if fc.name == "memory_search":
                    results["memory_result"] = tool_result
                elif fc.name == "detective_investigate":
                    results["detective_result"] = tool_result
                # ツール結果をinput_itemsに追加
                observation = json.dumps(
                    tool_result or {"error": "ツール実行に失敗しました"},
                    ensure_ascii=False,
                    default=str,
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": fc.call_id,
                        "output": observation[:3000],
                    }
                )
        else:
            logger.warning(
                "Orchestrator: 最大ステップ数に到達 [%d]",
                thread.hn_id,
            )
            results["final_summary"] = "最大ステップ数に到達しました。"

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

    def _parse_response_output(self, output: list[Any]) -> tuple[str, list[Any], str]:
        """Responses APIのoutputを解析.

        Args:
            output: response.output配列

        Returns:
            (reasoning_text, function_calls, conclusion_text)
        """
        reasoning_text = ""
        function_calls = []
        conclusion_text = ""

        for item in output:
            if item.type == "reasoning":
                # reasoning summaryからテキストを結合
                if hasattr(item, "summary") and item.summary:
                    reasoning_text = " ".join(
                        s.text for s in item.summary if hasattr(s, "text")
                    )
            elif item.type == "function_call":
                function_calls.append(item)
            elif item.type == "message" and hasattr(item, "content") and item.content:
                for content_part in item.content:
                    if hasattr(content_part, "text"):
                        conclusion_text += content_part.text

        return reasoning_text, function_calls, conclusion_text

    def _finalize_trace(self, thread: HNThread, results: dict[str, Any]) -> None:
        """Orchestratorの判断フローをLangfuseスパンに記録."""
        try:
            from langfuse import get_client

            client = get_client()

            decision_log = []
            for step_info in results.get("steps", []):
                action = step_info.get("action", "unknown")
                step_num = step_info.get("step", 0)
                reasoning = step_info.get("reasoning", "")

                if action == "conclusion":
                    entry = f"Step {step_num}: 結論を出力"
                else:
                    success = step_info.get("success", False)
                    status = "成功" if success else "失敗"
                    entry = f"Step {step_num}: {action} を実行 → {status}"

                if reasoning:
                    entry += f"\n  理由: {reasoning[:200]}"

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

    def _execute_tool(self, tool_name: str, thread: HNThread) -> dict[str, Any] | None:
        """ツールを実行."""
        agent_map = {
            "memory_search": ("hn-agent/memory", self.memory_agent),
            "detective_investigate": ("hn-agent/detective", self.detective_agent),
        }

        entry = agent_map.get(tool_name)
        if entry is None:
            logger.warning("未知のツール: %s", tool_name)
            return None

        span_name, agent = entry
        return self._run_agent(span_name, agent, thread)

    @observe()
    def _run_agent(
        self, name: str, agent: Any, thread: HNThread
    ) -> dict[str, Any] | None:
        """エージェントを@observeスパン内で実行."""
        from langfuse import get_client

        client = get_client()
        client.update_current_span(name=name)

        try:
            return agent.investigate(thread)
        except Exception:
            logger.exception("エージェント実行エラー: %s [%d]", name, thread.hn_id)
            return None

    def _send_notifications(self, results: dict[str, Any]) -> None:
        """調査結果をSlackに通知."""
        if results.get("memory_result"):
            self.reporter.report_memory(results["memory_result"])

        if results.get("detective_result"):
            self.reporter.report_detective(results["detective_result"])
