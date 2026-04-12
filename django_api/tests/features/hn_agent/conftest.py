"""HN Agent テスト共通フィクスチャ."""

import pytest

from features.hn_agent.models import HNAgentConfig
from integrations.langfuse.models import LangfusePromptRef


@pytest.fixture
def hn_prompt_refs(db):
    """HN Agent 用の 4 種の LangfusePromptRef を用意する.

    data migration でシード済みのものを取得する（テスト DB にも適用される）。
    """
    names = {
        "orchestrator_system": "hn-agent-orchestrator-system",
        "orchestrator_user": "hn-agent-orchestrator-user",
        "detective_system": "hn-agent-detective-system",
        "detective_user": "hn-agent-detective-user",
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
    )
