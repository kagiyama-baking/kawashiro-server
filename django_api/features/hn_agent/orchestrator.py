"""Orchestrator — LangGraph ReAct AgentでDetective Agentを制御."""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langfuse import observe
from langgraph.prebuilt import create_react_agent

from integrations.langfuse.client import resolve_prompt
from integrations.llm.config import get_llm_settings

from .agents.detective import DetectiveAgent
from .agents.devils_advocate import DevilsAdvocateAgent
from .agents.security_responder import SecurityResponderAgent
from .models import HNAgentConfig, HNThread
from .reporter import Reporter

logger = logging.getLogger(__name__)

MAX_STEPS = 10


class Orchestrator:
    """LangGraph ReAct AgentベースでDetective Agentを制御するオーケストレーター."""

    def __init__(
        self,
        detective_agent: DetectiveAgent | None = None,
        devils_advocate_agent: DevilsAdvocateAgent | None = None,
        security_responder_agent: SecurityResponderAgent | None = None,
        reporter: Reporter | None = None,
    ):
        """初期化."""
        self._detective_agent = detective_agent
        self._devils_advocate_agent = devils_advocate_agent
        self._security_responder_agent = security_responder_agent
        self._reporter = reporter

    @property
    def detective_agent(self) -> DetectiveAgent:
        """Detective Agentを取得（遅延初期化）."""
        if self._detective_agent is None:
            self._detective_agent = DetectiveAgent()
        return self._detective_agent

    @property
    def devils_advocate_agent(self) -> DevilsAdvocateAgent:
        """Devil's Advocate Agentを取得（遅延初期化）."""
        if self._devils_advocate_agent is None:
            self._devils_advocate_agent = DevilsAdvocateAgent()
        return self._devils_advocate_agent

    @property
    def security_responder_agent(self) -> SecurityResponderAgent:
        """Security Responder Agentを取得（遅延初期化）."""
        if self._security_responder_agent is None:
            self._security_responder_agent = SecurityResponderAgent()
        return self._security_responder_agent

    @property
    def reporter(self) -> Reporter:
        """Reporterを取得（遅延初期化）."""
        if self._reporter is None:
            self._reporter = Reporter()
        return self._reporter

    @observe(name="hn-agent/orchestrator", as_type="agent")
    def investigate(self, thread: HNThread) -> dict[str, Any]:
        """スレッドの調査をオーケストレーション.

        LangGraph ReAct Agentがツール呼び出しを自律的に判断し、
        Detective Agentを実行する。

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
            "detective_result": None,
            "devils_advocate_result": None,
            "security_responder_result": None,
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

        # いずれかのエージェントが結果を返した場合のみ調査済みマーク
        # （セキュリティ単独・Detective単独・複数呼び出しすべてに対応）
        if any(
            results.get(key)
            for key in (
                "detective_result",
                "devils_advocate_result",
                "security_responder_result",
            )
        ):
            thread.is_investigated = True
            thread.save(update_fields=["is_investigated"])

        # Slack通知
        self._send_notifications(results)

        logger.info(
            "Orchestrator終了: [%d] %d steps",
            thread.hn_id,
            len(results["steps"]),
        )
        return results

    def _run_agent(self, thread: HNThread, results: dict[str, Any]) -> dict[str, Any]:
        """LangGraph ReAct Agentを構築・実行."""
        settings = get_llm_settings("orchestrator")
        agent_config = HNAgentConfig.objects.get_active_config()

        llm = ChatOpenAI(
            base_url=settings.proxy_base_url,
            api_key=settings.proxy_api_key,
            model=settings.model_alias,
            timeout=settings.timeout,
            extra_body={
                "metadata": {
                    "service_name": settings.service_name,
                    "environment": settings.environment,
                }
            },
        )

        detective_agent = self.detective_agent
        devils_advocate_agent = self.devils_advocate_agent
        security_responder_agent = self.security_responder_agent

        @tool
        def detective_investigate() -> str:
            """スレッドが急上昇している理由を汎用的に調査する。
            タイトル和訳、注目理由、背景情報、HNコメントのハイライトを整理する。
            一般的なニュース・話題性のある記事で使う。"""
            try:
                result = detective_agent.investigate(thread)
                results["detective_result"] = result
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                logger.exception("Detective Agent実行エラー: [%d]", thread.hn_id)
                return json.dumps({"error": "Detective Agent実行に失敗しました"})

        @tool
        def devils_advocate_analyze() -> str:
            """新しい技術・プロダクト発表（Show HN）、アーキテクチャ議論など、
            新規性の高いスレッドに対して HN民の辛口・批判的な視点を抽出する。
            懸念点・トレードオフ・過去の類似事例・批判的コメントを整理する。
            detective_investigate と併用することが多い。"""
            try:
                result = devils_advocate_agent.analyze(thread)
                results["devils_advocate_result"] = result
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                logger.exception("Devil's Advocate Agent実行エラー: [%d]", thread.hn_id)
                return json.dumps({"error": "Devil's Advocate Agent実行に失敗しました"})

        @tool
        def security_responder_analyze() -> str:
            """脆弱性・CVE・情報漏洩・ハッキング・ゼロデイなど、セキュリティ
            インシデントのスレッドに対して、影響範囲・回避策・公式パッチ・CVE ID
            を整理してエンジニアの対応方針を明確化する。
            セキュリティ話題ではこのツール単独で完結させてよい（detective は不要）。"""
            try:
                result = security_responder_agent.analyze(thread)
                results["security_responder_result"] = result
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                logger.exception(
                    "Security Responder Agent実行エラー: [%d]", thread.hn_id
                )
                return json.dumps(
                    {"error": "Security Responder Agent実行に失敗しました"}
                )

        agent = create_react_agent(
            llm,
            [
                detective_investigate,
                devils_advocate_analyze,
                security_responder_analyze,
            ],
        )

        system_prompt = resolve_prompt(agent_config.orchestrator_system_prompt)
        user_content = resolve_prompt(
            agent_config.orchestrator_user_prompt,
            **self._build_user_variables(thread),
        )

        config: dict[str, Any] = {
            "recursion_limit": MAX_STEPS * 2 + 1,
        }

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
        tool_result_map = {
            "detective_investigate": "detective_result",
            "devils_advocate_analyze": "devils_advocate_result",
            "security_responder_analyze": "security_responder_result",
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

    def _build_user_variables(self, thread: HNThread) -> dict[str, str]:
        """Orchestrator ユーザープロンプトの変数を組み立てる."""
        snapshot = thread.latest_snapshot
        score_info = ""
        if snapshot:
            score_info = (
                f"スコア: {snapshot.score}, コメント数: {snapshot.num_comments}"
            )

        return {
            "hn_id": str(thread.hn_id),
            "title": thread.title,
            "url": thread.url or "(self-post)",
            "author": thread.author,
            "score_info": score_info,
        }

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
        if results.get("detective_result"):
            self.reporter.report_detective(results["detective_result"])
        if results.get("devils_advocate_result"):
            self.reporter.report_devils_advocate(results["devils_advocate_result"])
        if results.get("security_responder_result"):
            self.reporter.report_security_responder(
                results["security_responder_result"]
            )
