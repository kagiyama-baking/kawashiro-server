"""テスト中に実 LLM・Langfuse へ送信しないためのガードのテスト."""

import os

import pydantic_ai.models
import pytest


@pytest.mark.unit
def test_allow_model_requests_during_tests_is_disabled():
    """conftest で実モデルへのリクエストが禁止されている."""
    assert pydantic_ai.models.ALLOW_MODEL_REQUESTS is False


@pytest.mark.unit
def test_langfuse_tracing_during_tests_is_disabled():
    """開発者の .env に Langfuse キーがあってもトレースを送らない."""
    assert os.environ["LANGFUSE_TRACING_ENABLED"] == "false"
