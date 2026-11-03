"""Orchestrator — PydanticAI のエージェントでサブエージェントを制御."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from langfuse import observe
from pydantic_ai import Agent, AgentRunResult, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import UsageLimits

from integrations.langfuse.client import resolve_prompt
from integrations.llm.config import get_llm_settings
from integrations.llm.runtime import run_agent_sync

from .agents import hn_conversation_id
from .agents.detective import DetectiveAgent
from .agents.devils_advocate import DevilsAdvocateAgent
from .agents.security_responder import SecurityResponderAgent
from .models import HNAgentConfig, HNThread
from .reporter import Reporter

logger = logging.getLogger(__name__)

MAX_STEPS = 10

# ツール呼び出しステップから結果キーへの対応（失敗判定に使う）
_TOOL_RESULT_KEYS = {
    "detective_investigate": "detective_result",
    "devils_advocate_analyze": "devils_advocate_result",
    "security_responder_analyze": "security_responder_result",
}


@dataclass(frozen=True)
class OrchestratorDeps:
    """ツールへ渡す実行ごとの依存."""

    thread: HNThread
    results: dict[str, Any]
    detective_agent: DetectiveAgent
    devils_advocate_agent: DevilsAdvocateAgent
    security_responder_agent: SecurityResponderAgent


class _IgnoreToolArguments(AbstractCapability[OrchestratorDeps]):
    """ツールの引数を検証せずに捨てる.

    どのツールも引数を取らないので、モデルが余計な引数を付けてもそのまま実行する。
    検証すると再試行を消費し、超過すると調査全体が失敗して次のポーリングで再実行される。
    """

    async def before_tool_validate(
        self,
        ctx: RunContext[OrchestratorDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: Any,
    ) -> dict[str, Any]:
        """引数を空にする."""
        return {}


# 出力に None を許し、ツールの後に本文がなくても再試行せず結論なしで終える
ORCHESTRATOR_AGENT = Agent(
    name="hn-orchestrator",
    deps_type=OrchestratorDeps,
    output_type=str | None,
    capabilities=[_IgnoreToolArguments()],
)


# ツールの関数名と docstring は Langfuse 上のプロンプトとの契約なので変えない
# （integrations/langfuse/migrations/0003_seed_new_agent_refs.py）。
# サブエージェントを実行するので async にする（同期ツールの中では実行できない）。
@ORCHESTRATOR_AGENT.tool
async def detective_investigate(ctx: RunContext[OrchestratorDeps]) -> str:
    """スレッドが急上昇している理由を汎用的に調査する。
    タイトル和訳、注目理由、背景情報、HNコメントのハイライトを整理する。
    一般的なニュース・話題性のある記事で使う。"""
    deps = ctx.deps
    try:
        result = await deps.detective_agent.investigate(deps.thread)
        deps.results["detective_result"] = result
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        logger.exception("Detective Agent実行エラー: [%d]", deps.thread.hn_id)
        return json.dumps({"error": "Detective Agent実行に失敗しました"})


@ORCHESTRATOR_AGENT.tool
async def devils_advocate_analyze(ctx: RunContext[OrchestratorDeps]) -> str:
    """新しい技術・プロダクト発表（Show HN）、アーキテクチャ議論など、
    新規性の高いスレッドに対して HN民の辛口・批判的な視点を抽出する。
    懸念点・トレードオフ・過去の類似事例・批判的コメントを整理する。
    detective_investigate と併用することが多い。"""
    deps = ctx.deps
    try:
        result = await deps.devils_advocate_agent.analyze(deps.thread)
        deps.results["devils_advocate_result"] = result
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        logger.exception("Devil's Advocate Agent実行エラー: [%d]", deps.thread.hn_id)
        return json.dumps({"error": "Devil's Advocate Agent実行に失敗しました"})


@ORCHESTRATOR_AGENT.tool
async def security_responder_analyze(ctx: RunContext[OrchestratorDeps]) -> str:
    """脆弱性・CVE・情報漏洩・ハッキング・ゼロデイなど、セキュリティ
    インシデントのスレッドに対して、影響範囲・回避策・公式パッチ・CVE ID
    を整理してエンジニアの対応方針を明確化する。
    セキュリティ話題ではこのツール単独で完結させてよい（detective は不要）。"""
    deps = ctx.deps
    try:
        result = await deps.security_responder_agent.analyze(deps.thread)
        deps.results["security_responder_result"] = result
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        logger.exception("Security Responder Agent実行エラー: [%d]", deps.thread.hn_id)
        return json.dumps({"error": "Security Responder Agent実行に失敗しました"})


class Orchestrator:
    """PydanticAI のエージェントでサブエージェントを制御するオーケストレーター."""

    def __init__(
        self,
        detective_agent: DetectiveAgent | None = None,
        devils_advocate_agent: DevilsAdvocateAgent | None = None,
        security_responder_agent: SecurityResponderAgent | None = None,
        reporter: Reporter | None = None,
        notify: bool = True,
    ):
        """初期化.

        Args:
            detective_agent: Detective Agent（省略時は遅延生成）
            devils_advocate_agent: Devil's Advocate Agent（省略時は遅延生成）
            security_responder_agent: Security Responder Agent（省略時は遅延生成）
            reporter: 通知に使う Reporter（省略時は遅延生成）
            notify: False なら調査結果を Slack へ送らない（Reporter も作らない）
        """
        self._detective_agent = detective_agent
        self._devils_advocate_agent = devils_advocate_agent
        self._security_responder_agent = security_responder_agent
        self._reporter = reporter
        self._notify = notify

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

        エージェントがツール呼び出しを自律的に判断し、サブエージェントを実行する。

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
            self._extract_results(agent_output.all_messages(), results)
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

    def _run_agent(
        self, thread: HNThread, results: dict[str, Any]
    ) -> AgentRunResult[str | None]:
        """エージェントを実行する（ツールが results に結果を書き込む）."""
        settings = get_llm_settings("orchestrator")
        agent_config = HNAgentConfig.objects.get_active_config()

        deps = OrchestratorDeps(
            thread=thread,
            results=results,
            detective_agent=self.detective_agent,
            devils_advocate_agent=self.devils_advocate_agent,
            security_responder_agent=self.security_responder_agent,
        )

        system_prompt = resolve_prompt(agent_config.orchestrator_system_prompt)
        user_content = resolve_prompt(
            agent_config.orchestrator_user_prompt,
            **self._build_user_variables(thread),
        )

        return run_agent_sync(
            ORCHESTRATOR_AGENT,
            settings,
            user_prompt=user_content,
            instructions=system_prompt,
            deps=deps,
            usage_limits=UsageLimits(
                request_limit=MAX_STEPS + 1, tool_calls_limit=MAX_STEPS
            ),
            # 未知のツール名はモデルへ伝えて続行させる（打ち切りは usage_limits に任せる）
            retries={"tools": MAX_STEPS},
            conversation_id=hn_conversation_id(thread),
            # 推論深度は Orchestrator だけに指定する（空文字は「無効」で、送らない）
            reasoning_effort=agent_config.reasoning_effort or None,
        )

    def _extract_results(
        self, messages: list[ModelMessage], results: dict[str, Any]
    ) -> None:
        """実行の全メッセージからステップ情報と最終サマリーを抽出."""
        step_num = 0

        for msg in messages:
            if not isinstance(msg, ModelResponse):
                continue
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    step_num += 1
                    results["steps"].append(
                        {
                            "step": step_num,
                            "action": tool_call.tool_name,
                            "success": True,
                        }
                    )
            elif msg.text:
                step_num += 1
                results["steps"].append(
                    {
                        "step": step_num,
                        "action": "conclusion",
                        "content": msg.text,
                    }
                )
                results["final_summary"] = msg.text

        # ツールエラーチェック
        for step in results["steps"]:
            result_key = _TOOL_RESULT_KEYS.get(step["action"])
            if result_key and results[result_key] is None:
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
        """調査結果をSlackに通知（notify=False なら何もしない）."""
        if not self._notify:
            logger.info("Slack通知を抑止: [%d]", results["thread_hn_id"])
            return
        if results.get("detective_result"):
            self.reporter.report_detective(results["detective_result"])
        if results.get("devils_advocate_result"):
            self.reporter.report_devils_advocate(results["devils_advocate_result"])
        if results.get("security_responder_result"):
            self.reporter.report_security_responder(
                results["security_responder_result"]
            )
