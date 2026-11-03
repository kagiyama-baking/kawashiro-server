"""HN Agent テスト共通フィクスチャ."""

from unittest.mock import AsyncMock, patch

import pytest

from features.hn_agent.models import HNAgentConfig, HNThread
from features.hn_agent.orchestrator import ORCHESTRATOR_AGENT
from integrations.langfuse.models import LangfusePromptRef
from integrations.llm.models import LLMProviderConfig, LLMServiceConfig
from tests.fixtures.llm import ScriptedLLM, tool_calls


@pytest.fixture
def hn_llm_services(db):
    """HN Agent の全サービスに LLM 設定を割り当てる.

    接続設定はサブエージェントの準備処理の中で DB から読むので、実データを用意する。
    モデルは各テストで `Agent.override` するので LiteLLM へは接続しない。
    """
    provider = LLMProviderConfig.objects.create(
        name="hn-agent-test", model_alias="test-alias"
    )
    return {
        service_name: LLMServiceConfig.objects.create(
            service_name=service_name, provider_config=provider
        )
        for service_name in (
            "orchestrator",
            "detective",
            "devils_advocate",
            "security_responder",
        )
    }


@pytest.fixture
def hn_prompt_refs(db):
    """HN Agent 用の LangfusePromptRef を用意する.

    data migration でシード済みのものを取得する（テスト DB にも適用される）。
    """
    names = {
        "orchestrator_system": "hn-agent-orchestrator-system",
        "orchestrator_user": "hn-agent-orchestrator-user",
        "detective_system": "hn-agent-detective-system",
        "detective_user": "hn-agent-detective-user",
        "devils_advocate_system": "hn-agent-devils-advocate-system",
        "devils_advocate_user": "hn-agent-devils-advocate-user",
        "security_responder_system": "hn-agent-security-responder-system",
        "security_responder_user": "hn-agent-security-responder-user",
    }
    return {
        key: LangfusePromptRef.objects.get(name=name) for key, name in names.items()
    }


@pytest.fixture
def hn_agent_config(hn_prompt_refs):
    """有効な HNAgentConfig インスタンスを用意."""
    return HNAgentConfig.objects.create(
        name="test-config",
        is_active=True,
        score_threshold=100,
        velocity_threshold=50.0,
        poll_interval_seconds=600,
        front_page_limit=30,
        orchestrator_system_prompt=hn_prompt_refs["orchestrator_system"],
        orchestrator_user_prompt=hn_prompt_refs["orchestrator_user"],
        detective_system_prompt=hn_prompt_refs["detective_system"],
        detective_user_prompt=hn_prompt_refs["detective_user"],
        devils_advocate_system_prompt=hn_prompt_refs["devils_advocate_system"],
        devils_advocate_user_prompt=hn_prompt_refs["devils_advocate_user"],
        security_responder_system_prompt=hn_prompt_refs["security_responder_system"],
        security_responder_user_prompt=hn_prompt_refs["security_responder_user"],
    )


@pytest.fixture
def reporter_class():
    """Orchestrator が遅延生成する Reporter を差し替え、生成と送信を記録する."""
    with patch("features.hn_agent.orchestrator.Reporter") as reporter_class:
        yield reporter_class


@pytest.fixture
def investigation_thread(hn_llm_services, hn_agent_config):
    """調査すると Detective の結果が 1 件出るスレッドを用意する.

    引数なしで Orchestrator を作る入口（API・管理コマンド）のテスト用。モデルは台本で、
    遅延生成される Detective も差し替えるので、LLM・HN・Tavily・Langfuse へは出ない。
    """
    thread = HNThread.objects.create(
        hn_id=900,
        title="Notify Test Thread",
        url="https://example.com/notify",
        author="tester",
    )
    llm = ScriptedLLM(tool_calls("detective_investigate"), "結論")
    with (
        ORCHESTRATOR_AGENT.override(model=llm.model),
        patch("features.hn_agent.orchestrator.DetectiveAgent") as detective_class,
        patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")),
    ):
        detective_class.return_value.investigate = AsyncMock(
            return_value={
                "thread_hn_id": thread.hn_id,
                "thread_title": thread.title,
                "analysis": {"title_ja": "通知テスト"},
            }
        )
        yield thread
