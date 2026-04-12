"""LangfusePromptRef モデルのテスト."""

import pytest
from django.db.utils import IntegrityError

from integrations.langfuse.models import LangfusePromptRef


@pytest.mark.integration
@pytest.mark.django_db
class TestLangfusePromptRefModel:
    """LangfusePromptRef のモデルテスト."""

    def test_creates_with_defaults(self):
        """デフォルト値で作成できる."""
        ref = LangfusePromptRef.objects.create(
            name="test-ref",
            langfuse_prompt_name="test-prompt",
        )
        assert ref.name == "test-ref"
        assert ref.langfuse_prompt_name == "test-prompt"
        assert ref.label == "production"
        assert ref.fallback_text == ""
        assert ref.description == ""

    def test_name_is_unique(self):
        """name は unique 制約."""
        LangfusePromptRef.objects.create(
            name="duplicate",
            langfuse_prompt_name="a",
        )
        with pytest.raises(IntegrityError):
            LangfusePromptRef.objects.create(
                name="duplicate",
                langfuse_prompt_name="b",
            )

    def test_str_returns_name_and_prompt(self):
        """__str__ は識別名と Langfuse プロンプト名を含む."""
        ref = LangfusePromptRef.objects.create(
            name="foo",
            langfuse_prompt_name="bar",
            label="staging",
        )
        assert str(ref) == "foo (bar@staging)"
