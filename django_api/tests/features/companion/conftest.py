"""Companion のテストの共通フィクスチャ."""

import pytest


@pytest.fixture(autouse=True)
def langfuse_prompts(langfuse_prompts):
    """Langfuse のプロンプトの代役（tests/conftest.py）を、companion のテスト全部に使う.

    autouse なので、companion のテストは Langfuse へ出ない。入れていない名前・ラベルは
    SDK と同じく NotFoundError で取得に失敗する（システムプロンプトは `resolve_prompt` が
    参照のフォールバックテキストに落とし、スキルの本文は PromptUnavailableError になる）。
    """
    return langfuse_prompts
