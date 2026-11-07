"""Prompts（Prompt。全エージェントで共有するプロンプト）のモデルのテスト."""

import pytest
from django.db.utils import IntegrityError

from integrations.llm.models import Prompt


@pytest.mark.unit
class TestPromptLocation:
    """モデルの置き場所（admin のグループ）・表・表示名."""

    def test_prompt_app_label_is_llm_config(self):
        """llm_config アプリのモデル（admin では AI設定のグループに出る）."""
        assert Prompt._meta.app_label == "llm_config"

    def test_prompt_db_table_is_table_created_by_langfuse_integration(self):
        """表は langfuse_integration の migration が作った表のまま（状態だけ移した）."""
        assert Prompt._meta.db_table == "langfuse_integration_langfusepromptref"

    def test_prompt_verbose_names_are_prompt_and_prompts(self):
        """admin には「Prompts」と出る."""
        assert (Prompt._meta.verbose_name, Prompt._meta.verbose_name_plural) == (
            "Prompt",
            "Prompts",
        )


@pytest.mark.integration
@pytest.mark.django_db
class TestPromptModel:
    """プロンプトの既定値・一意・表示."""

    def test_creates_with_defaults(self):
        """ラベルの既定は production、説明とフォールバックテキストは空."""
        prompt = Prompt.objects.create(name="test-ref", langfuse_prompt_name="test")

        assert (prompt.label, prompt.fallback_text, prompt.description) == (
            "production",
            "",
            "",
        )

    def test_name_is_unique(self):
        """名前は一意."""
        Prompt.objects.create(name="duplicate", langfuse_prompt_name="a")

        with pytest.raises(IntegrityError):
            Prompt.objects.create(name="duplicate", langfuse_prompt_name="b")

    def test_str_returns_name_and_prompt(self):
        """表示は識別名と、Langfuse のプロンプト名@ラベル."""
        prompt = Prompt.objects.create(
            name="foo", langfuse_prompt_name="bar", label="staging"
        )

        assert str(prompt) == "foo (bar@staging)"
