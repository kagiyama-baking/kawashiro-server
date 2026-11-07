"""実際に Langfuse の計装を有効にして HN 調査・Talk・Companion を実行し、スパンを JSON で出力する.

`tests/integrations/llm/test_tracing.py` がサブプロセスで実行する。Langfuse のクライアントは
プロセス内で共有され、テストのプロセスではトレースを無効にしているので分離する。
モデルは FunctionModel か HTTP 層だけの代役、エクスポーターはメモリ上なので、
LLM にも Langfuse にも送信しない。
"""

import json
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

# Companion の音声合成の代役が返す音声（UTF-8 として読めるので、記録されれば文字列で現れる）
COMPANION_AUDIO = b"RIFF-companion-trace-audio"
# Companion を実行する時刻（日本時間では 2026-11-07 12:00）と、その日の Langfuse のセッション ID
COMPANION_NOW = datetime(2026, 11, 7, 3, 0, tzinfo=UTC)
COMPANION_SESSION_ID = "companion/2026-11-07"


def _span_to_dict(span) -> dict:
    return {
        "name": span.name,
        "span_id": span.context.span_id,
        "trace_id": span.context.trace_id,
        "parent_id": span.parent.span_id if span.parent else None,
        "scope": span.instrumentation_scope.name,
        "status": span.status.status_code.name,
        "attributes": {key: str(value) for key, value in span.attributes.items()},
    }


def _create_fixtures():
    """調査に必要な最小限のデータを作る."""
    from features.hn_agent.models import HNAgentConfig, HNThread, HNThreadSnapshot
    from integrations.llm.models import LLMProviderConfig, LLMServiceConfig, Prompt

    provider = LLMProviderConfig.objects.create(name="trace", model_alias="test-alias")
    for service_name in ("orchestrator", "detective", "talk", "companion"):
        LLMServiceConfig.objects.create(
            service_name=service_name, provider_config=provider
        )

    refs = {
        field: Prompt.objects.get(name=name)
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
    """Talk のチャットをストリーミングで session_id 付きで実行する."""
    from features.talk.llm_agents import TALK_CHAT_AGENT
    from features.talk.models import TalkSetting
    from features.talk.services import TalkService
    from integrations.llm.models import Prompt
    from tests.fixtures.llm import ScriptedLLM

    ref = Prompt.objects.create(name="trace-talk", langfuse_prompt_name="trace-talk")
    setting = TalkSetting.objects.create(name="trace", system_prompt=ref)
    llm = ScriptedLLM("返信")
    service = TalkService()
    with TALK_CHAT_AGENT.override(model=llm.model):
        system_prompt = service.prepare_chat_prompt(setting)
        list(
            service.stream_chat_reply(
                system_prompt,
                [{"role": "user", "content": "hi"}],
                session_id="trace-session",
            )
        )


def _run_talk_through_litellm():
    """HTTP 層だけ差し替えて、LiteLLM の応答の解釈まで通すチャットを実行する.

    最後まで読むものと、途中で閉じるもの（停止・切断）の 2 本を実行する。
    """
    from pydantic_ai.models import override_allow_model_requests

    from features.talk.services import TalkService
    from tests.fixtures.llm import FakeLiteLLM, LiteLLMStreamBody, litellm_stream

    fake = FakeLiteLLM(
        litellm_stream(
            "本文",
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 3,
                "total_tokens": 13,
                "completion_tokens_details": {"text_tokens": 2, "reasoning_tokens": 1},
            },
        ),
        LiteLLMStreamBody("途中", hang=True).response(),
    )
    messages = [{"role": "user", "content": "hi"}]
    service = TalkService()
    with (
        patch("integrations.llm.runtime.AsyncOpenAI", side_effect=fake.build_client),
        override_allow_model_requests(True),
    ):
        list(service.stream_chat_reply("s", messages, session_id="litellm-session"))
        stream = service.stream_chat_reply("s", messages, session_id="stopped-session")
        next(stream)
        stream.close()


def _run_companion():
    """Companion をスキルの読み込みと音声合成つきで実行する（音声は代役が返す）.

    スキルの本文の取得（`fetch_text_prompt`）も Langfuse サーバーへ出ないよう差し替える
    （システムプロンプトは main の差し替えで解決する）。セッション ID が決まるよう、
    Django の現在時刻は COMPANION_NOW に固定する。
    """
    from features.companion.agent import COMPANION_AGENT
    from features.companion.models import CompanionConfig
    from features.companion.services import run_companion
    from integrations.llm.models import AgentSkill, Prompt
    from integrations.llm.runtime import _LITELLM_PROFILE
    from integrations.tts.client import TTSResult
    from tests.fixtures.llm import ScriptedLLM, load_capability

    ref = Prompt.objects.create(
        name="trace-companion", langfuse_prompt_name="trace-companion"
    )
    config = CompanionConfig.objects.create(
        name="trace", is_active=True, system_prompt=ref, tts_enabled=True
    )
    config.skills.add(
        AgentSkill.objects.create(name="good-morning", description="朝のあいさつ")
    )
    llm = ScriptedLLM(
        load_capability("good-morning"), "おはよう！", profile=_LITELLM_PROFILE
    )
    with (
        COMPANION_AGENT.override(model=llm.model),
        patch("integrations.llm.skills.fetch_text_prompt", return_value="手順"),
        patch("features.companion.services.TTSClient") as tts_client,
        patch("django.utils.timezone.now", return_value=COMPANION_NOW),
    ):
        tts_client.return_value.synthesize.return_value = TTSResult(
            audio_data=COMPANION_AUDIO, content_type="audio/wav", format="wav"
        )
        run_companion("おはよう")


def main() -> None:
    """スパンを収集して標準出力へ JSON で書く."""
    import django

    django.setup()

    import pydantic_ai.models
    from django.test.utils import setup_databases
    from langfuse import Langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    # 実モデルへのリクエストは許可しない（モデルか HTTP 層を差し替えたものだけが動く）
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = False

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
        _run_talk_through_litellm()
        _run_companion()

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
