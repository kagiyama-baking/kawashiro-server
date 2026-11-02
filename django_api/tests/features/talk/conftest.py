"""Talk テスト共通フィクスチャ."""

from unittest.mock import patch

import pytest

from integrations.langfuse.models import LangfusePromptRef
from tests.fixtures.llm import make_llm_settings


@pytest.fixture
def talk_llm_settings():
    """LLM 接続設定を固定する（DB の LLMServiceConfig に依存させない）."""
    with patch(
        "features.talk.services.get_llm_settings",
        return_value=make_llm_settings("talk"),
    ) as mock_get_settings:
        yield mock_get_settings


@pytest.fixture
def talk_prompt_refs(db):
    """テスト用システム/ユーザープロンプト参照を用意する.

    TalkConfig に付ける汎用参照。fallback_text はテンプレート変数
    `{{weather}}` `{{events}}` `{{datetime}}` を含める。
    """
    system_ref = LangfusePromptRef.objects.create(
        name="talk-test-system",
        langfuse_prompt_name="talk-test-system",
        fallback_text="テスト用システムプロンプト",
    )
    user_ref = LangfusePromptRef.objects.create(
        name="talk-test-user",
        langfuse_prompt_name="talk-test-user",
        fallback_text=(
            "テンプレ: weather={{weather}} events={{events}} datetime={{datetime}}"
        ),
    )
    return {"system": system_ref, "user": user_ref}
