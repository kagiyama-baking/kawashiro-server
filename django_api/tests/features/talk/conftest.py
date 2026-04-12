"""Talk テスト共通フィクスチャ."""

import pytest

from integrations.langfuse.models import LangfusePromptRef


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
