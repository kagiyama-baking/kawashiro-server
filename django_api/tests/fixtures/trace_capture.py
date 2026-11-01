"""実際に Langfuse の計装を有効にして HN 調査と Talk を実行し、スパンを JSON で出力する.

`tests/integrations/llm/test_tracing.py` がサブプロセスで実行する。Langfuse のクライアントは
プロセス内で共有され、テストのプロセスではトレースを無効にしているので分離する。
モデルは FunctionModel、エクスポーターはメモリ上なので、LLM にも Langfuse にも送信しない。
"""

import json
import sys
from unittest.mock import MagicMock, patch


def _span_to_dict(span) -> dict:
    return {
        "name": span.name,
        "span_id": span.context.span_id,
        "trace_id": span.context.trace_id,
        "parent_id": span.parent.span_id if span.parent else None,
        "scope": span.instrumentation_scope.name,
        "attributes": {key: str(value) for key, value in span.attributes.items()},
    }


def _create_fixtures():
    """調査に必要な最小限のデータを作る."""
    from features.hn_agent.models import HNAgentConfig, HNThread, HNThreadSnapshot
    from integrations.langfuse.models import LangfusePromptRef
    from integrations.llm.models import LLMProviderConfig, LLMServiceConfig

    provider = LLMProviderConfig.objects.create(name="trace", model_alias="test-alias")
    for service_name in ("orchestrator", "detective", "talk"):
        LLMServiceConfig.objects.create(
            service_name=service_name, provider_config=provider
        )

    refs = {
        field: LangfusePromptRef.objects.get(name=name)
        for field, name in {
            "orchestrator_system_prompt": "hn-agent-orchestrator-system",
            "orchestrator_user_prompt": "hn-agent-orchestrator-user",
            "detective_system_prompt": "hn-agent-detective-system",
            "detective_user_prompt": "hn-agent-detective-user",
            "devils_advocate_system_prompt": "hn-agent-devils-advocate-system",
            "devils_advocate_user_prompt": "hn-agent-devils-advocate-user",
            "security_responder_system_prompt": "hn-agent-security-responder-system",
            "security_responder_user_prompt": "hn-agent-security-responder-user",
        }.items()
    }
    HNAgentConfig.objects.create(name="trace", is_active=True, **refs)

    thread = HNThread.objects.create(hn_id=4242, title="Traced Thread", author="a")
    HNThreadSnapshot.objects.create(thread=thread, score=100, num_comments=1)
    return thread


def _run_investigation(thread):
    """Orchestrator → Detective をモデルだけ差し替えて実行する."""
    from features.hn_agent.agents.detective import DETECTIVE_AGENT, DetectiveAgent
    from features.hn_agent.orchestrator import ORCHESTRATOR_AGENT, Orchestrator
    from tests.fixtures.llm import ScriptedLLM, tool_calls

    hn_client = MagicMock()
    hn_client.get_comments.return_value = []
    hn_client.flatten_comments.return_value = []
    tavily_client = MagicMock()
    tavily_client.search_context.return_value = []

    orchestrator_llm = ScriptedLLM(tool_calls("detective_investigate"), "結論")
    detective_llm = ScriptedLLM('{"title_ja": "和訳", "comment_highlights": []}')
    orchestrator = Orchestrator(
        detective_agent=DetectiveAgent(
            hn_client=hn_client, tavily_client=tavily_client
        ),
        reporter=MagicMock(),
    )
    with (
        ORCHESTRATOR_AGENT.override(model=orchestrator_llm.model),
        DETECTIVE_AGENT.override(model=detective_llm.model),
    ):
        return orchestrator.investigate(thread)


def _run_talk():
    """Talk のチャットを session_id 付きで実行する."""
    from features.talk.llm_agents import TALK_CHAT_AGENT
    from features.talk.models import TalkConfig
    from features.talk.services import TalkService
    from integrations.langfuse.models import LangfusePromptRef
    from tests.fixtures.llm import ScriptedLLM

    ref = LangfusePromptRef.objects.create(
        name="trace-talk", langfuse_prompt_name="trace-talk", fallback_text="system"
    )
    config = TalkConfig.objects.create(
        name="trace",
        display_name="trace",
        system_prompt_ref=ref,
        user_prompt_ref=ref,
    )
    llm = ScriptedLLM("返信")
    with TALK_CHAT_AGENT.override(model=llm.model):
        TalkService().synthesize_chat(
            config=config,
            messages=[{"role": "user", "content": "hi"}],
            session_id="trace-session",
        )


def main() -> None:
    """スパンを収集して標準出力へ JSON で書く."""
    import django

    django.setup()

    from django.test.utils import setup_databases
    from langfuse import Langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    setup_databases(verbosity=0, interactive=False)

    exporter = InMemorySpanExporter()
    client = Langfuse(span_exporter=exporter)

    # プロンプトの取得だけ Langfuse サーバーへ出ないようにする（送信はしていない）
    with patch(
        "integrations.langfuse.client.get_prompt_with_variables",
        return_value=(lambda **_: "prompt", set()),
    ):
        thread = _create_fixtures()
        result = _run_investigation(thread)
        _run_talk()

    client.flush()
    json.dump(
        {
            "final_summary": result["final_summary"],
            "spans": [_span_to_dict(span) for span in exporter.get_finished_spans()],
        },
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
